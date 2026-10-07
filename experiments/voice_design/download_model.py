"""Download the official Qwen voice model into this experiment only."""
from pathlib import Path
import argparse
import json
import os
import hashlib
import math
import shutil
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = Path(__file__).resolve().parent
os.environ['HF_HOME'] = str(HERE / 'models/cache')
os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN'] = '1'
os.environ['HF_HUB_DISABLE_XET'] = '1'
os.environ['HF_HUB_DOWNLOAD_TIMEOUT'] = '30'

MODELS = {
    'design': 'Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign',
    'base': 'Qwen/Qwen3-TTS-12Hz-0.6B-Base',
}


def digest(path):
    checksum = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            checksum.update(block)
    return checksum.hexdigest()


def download_weight(repo, revision, item, destination, workers):
    """Resume bounded HTTP ranges and verify the complete official LFS hash."""
    target = destination / item.rfilename
    if not target.resolve().is_relative_to(destination.resolve()):
        raise ValueError('Weight path escaped the model directory')
    expected = item.lfs.sha256
    if target.exists() and target.stat().st_size == item.size and digest(target) == expected:
        print('Verified cached weight: '+item.rfilename, flush=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    # VoiceDesign and Base can share the exact speech tokenizer checkpoint.
    # Reuse only byte-identical, officially hashed weights; keep independent files.
    for sibling in destination.parent.iterdir():
        candidate = sibling/item.rfilename
        if sibling == destination or not candidate.is_file():
            continue
        if candidate.stat().st_size == item.size and digest(candidate) == expected:
            temporary = target.with_suffix('.reuse')
            shutil.copyfile(candidate, temporary)
            if digest(temporary) != expected:
                raise ValueError('Reused weight hash mismatch: '+item.rfilename)
            os.replace(temporary, target)
            print('Reused verified weight: '+item.rfilename, flush=True)
            return
    partial = target.with_suffix(target.suffix+'.part')
    journal = partial.with_suffix(partial.suffix+'.json')
    block_size = 16 * 1024 * 1024
    state = dict(sha256=expected, size=item.size, block_size=block_size, completed=[])
    if partial.exists() and journal.exists():
        candidate = json.loads(journal.read_text(encoding='utf-8'))
        if all(candidate.get(key) == state[key] for key in ('sha256', 'size', 'block_size')):
            state = candidate
    if not partial.exists() or partial.stat().st_size != item.size:
        with partial.open('wb') as stream:
            stream.truncate(item.size)
        state['completed'] = []
    completed = set(state['completed'])
    blocks = math.ceil(item.size/block_size)
    lock = threading.Lock()
    url = f'https://huggingface.co/{repo}/resolve/{revision}/{item.rfilename}'
    mirror = f'https://modelscope.cn/api/v1/models/{repo}/repo?Revision=master&FilePath={item.rfilename}'
    def fetch(index):
        start, end = index*block_size, min(item.size, (index+1)*block_size)-1
        for attempt in range(4):
            try:
                source_url = (url+f'?download=true&scott_chunk={index}&retry={attempt}') if attempt < 2 else mirror+f'&scott_chunk={index}&retry={attempt}'
                request = urllib.request.Request(source_url,
                                                 headers={'Range': f'bytes={start}-{end}'})
                with urllib.request.urlopen(request, timeout=30) as response:
                    if response.status != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{item.size}':
                        raise ValueError(f'Unexpected range: status={response.status}, content-range={response.headers.get("Content-Range")}')
                    content = response.read(end-start+1)
                if len(content) != end-start+1:
                    raise ValueError(f'Incomplete range: {len(content)}/{end-start+1} bytes')
                with partial.open('r+b') as stream:
                    stream.seek(start)
                    stream.write(content)
                    stream.flush()
                with lock:
                    completed.add(index)
                    state['completed'] = sorted(completed)
                    temporary = journal.with_suffix('.tmp')
                    temporary.write_text(json.dumps(state), encoding='utf-8')
                    os.replace(temporary, journal)
                    if len(completed) % 8 == 0 or len(completed) == blocks:
                        print(f'{item.rfilename}: {len(completed)}/{blocks} parts ({len(completed)/blocks:.0%})', flush=True)
                return
            except Exception as error:
                detail = ': '+str(error) if isinstance(error, ValueError) else ''
                print(f'Retry {item.rfilename} part {index}: {type(error).__name__}{detail}', flush=True)
                if attempt == 3:
                    raise RuntimeError(f'Could not download {item.rfilename} part {index}: {type(error).__name__}') from None
                time.sleep(1+attempt)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch, index) for index in range(blocks) if index not in completed]
        for future in as_completed(futures):
            future.result()
    if digest(partial) != expected:
        raise ValueError('Downloaded weight hash mismatch: '+item.rfilename)
    os.replace(partial, target)
    journal.unlink(missing_ok=True)
    print('SHA256 verified: '+item.rfilename, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=MODELS, default='design')
    parser.add_argument('--workers', type=int, choices=range(1, 17), default=4)
    args = parser.parse_args()
    from huggingface_hub import HfApi, snapshot_download
    destination = HERE / 'models' / args.kind
    manifest = destination / 'scott-model.json'
    repo = MODELS[args.kind]
    plan = destination / 'scott-download-plan.json'
    pinned = manifest if manifest.exists() else plan
    revision = json.loads(pinned.read_text(encoding='utf-8'))['revision'] if pinned.exists() else None
    info = HfApi(token=False).model_info(repo, revision=revision, files_metadata=True)
    destination.mkdir(parents=True, exist_ok=True)
    plan.write_text(json.dumps(dict(model=repo, revision=info.sha)), encoding='utf-8')
    total = sum(item.size or 0 for item in info.siblings)
    print(json.dumps(dict(model=repo, revision=info.sha, download_gib=round(total / 2**30, 2))), flush=True)
    snapshot_download(repo, revision=info.sha, local_dir=destination,
                      cache_dir=HERE/'models/cache/hub', token=False, max_workers=2,
                      allow_patterns=['*.json', '*.txt', '*.model', '*.tiktoken', '*.npz', 'LICENSE', 'README.md'])
    for item in info.siblings:
        if item.rfilename.endswith('.safetensors'):
            download_weight(repo, info.sha, item, destination, args.workers)
    candidate = manifest.with_suffix('.tmp')
    candidate.write_text(json.dumps(dict(model=repo, revision=info.sha,
                                       files=[item.rfilename for item in info.siblings]), indent=2), encoding='utf-8')
    os.replace(candidate, manifest)
    print('Model ready: '+str(destination), flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
