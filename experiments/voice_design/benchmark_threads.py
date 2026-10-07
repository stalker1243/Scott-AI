"""Compare CPU thread counts in separate offline TTS processes, preserving the recipe."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
import time

from trial_utils import ROOT, cases, prepare_text, save_json, write_audio
sys.path.insert(0, str(ROOT/'backend'))
from scott_voice_engine import default_config
from scott_voice_install import REFERENCE_SHA, clean_environment


def child(args):
    import torch
    torch.set_num_threads(args.threads)
    from qwen_tts import Qwen3TTSModel
    config = default_config()
    reference = json.loads(config.reference_json.read_text(encoding='utf-8'))
    audio = config.reference_json.with_name('scott-reference.wav')
    assert hashlib.sha256(audio.read_bytes()).hexdigest() == REFERENCE_SHA
    start = time.perf_counter()
    model = Qwen3TTSModel.from_pretrained(str(config.model_dir),device_map='cuda',dtype=torch.bfloat16,
        attn_implementation='sdpa',local_files_only=True)
    prompt = model.create_voice_clone_prompt(ref_audio=str(audio),ref_text=reference['reference_text'],x_vector_only_mode=False)
    load_seconds = time.perf_counter()-start
    results = []
    for case in [c for c in cases() if c['id'] in args.cases]:
        measurements = []
        hashes = []
        for index in range(args.repeats+1):
            torch.manual_seed(20261006)
            torch.cuda.synchronize(); torch.cuda.reset_peak_memory_stats()
            start = time.perf_counter()
            with torch.inference_mode():
                waves, rate = model.generate_voice_clone(text=prepare_text(case['text']),language='Russian',
                    voice_clone_prompt=prompt,non_streaming_mode=False,max_new_tokens=768,
                    temperature=.7,top_p=.95,subtalker_temperature=.7)
            torch.cuda.synchronize()
            elapsed = time.perf_counter()-start
            path = args.output/f'threads-{args.threads}-{case["id"]}-{index}.wav'
            metrics = write_audio(waves[0],rate,path)
            hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
            measurements.append(elapsed)
            print(json.dumps(dict(threads=args.threads,case=case['id'],run=index,seconds=round(elapsed,3))),flush=True)
        results.append(dict(**case,**metrics,threads=args.threads,warmup_seconds=round(measurements[0],3),
            times_seconds=[round(t,3) for t in measurements[1:]],median_seconds=round(statistics.median(measurements[1:]),3),
            hashes=hashes,repeat_identical=len(set(hashes))==1,vram_peak_gib=round(torch.cuda.max_memory_allocated()/2**30,3)))
    result = dict(threads=args.threads,load_seconds=round(load_seconds,3),torch=torch.__version__,
        gpu=torch.cuda.get_device_name(),reference_sha256=REFERENCE_SHA,results=results)
    save_json(args.output/f'threads-{args.threads}.json',result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'reports/voice-threads')
    parser.add_argument('--threads',type=int,choices=[1,2,4,8])
    parser.add_argument('--candidates',nargs='+',type=int,choices=[1,2,4,8],default=[4,1,2,8])
    parser.add_argument('--cases',nargs='+',choices=['status','technical','numbers'],default=['status'])
    parser.add_argument('--repeats',type=int,choices=[2,3],default=2)
    args = parser.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    if args.threads:
        child(args); return
    config = default_config()
    env = clean_environment()
    env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONDONTWRITEBYTECODE='1')
    for threads in args.candidates:
        command = [str(config.python),str(Path(__file__).resolve()),'--threads',str(threads),'--output',str(args.output),
                   '--repeats',str(args.repeats),'--cases',*args.cases]
        subprocess.run(command,check=True,env=env,stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    data = [json.loads((args.output/f'threads-{n}.json').read_text(encoding='utf-8')) for n in args.candidates]
    baseline = next(r for r in data if r['threads']==4)
    for candidate in data:
        for row in candidate['results']:
            original = next(r for r in baseline['results'] if r['id']==row['id'])
            row['identical_to_original'] = row['repeat_identical'] and row['hashes'][0]==original['hashes'][0]
            row['speedup'] = round(original['median_seconds']/row['median_seconds'],3)
    save_json(args.output/'comparison.json',dict(candidates=data,reference_sha256=REFERENCE_SHA,
        note='Each candidate starts in a new process; warmup is excluded from the median. No SDK/model/settings changes.'))


if __name__=='__main__':
    main()
