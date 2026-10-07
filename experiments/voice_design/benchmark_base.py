"""Try the selected synthetic voice on Qwen Base and the live STT-only API."""
from pathlib import Path
import argparse
import hashlib
import json
import statistics
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor

from trial_utils import ROOT, HERE, cases, prepare_text, recognition_check, save_json, write_audio


class Backend:
    def __init__(self, url):
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise ValueError('The benchmark requires a local backend')
        self.url = url.rstrip('/')
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get(self, path, timeout=5):
        started = time.perf_counter()
        with self.opener.open(self.url+path, timeout=timeout) as response:
            value = json.load(response)
        return value, time.perf_counter()-started

    def transcribe(self, path, reference):
        boundary = 'scott-'+uuid.uuid4().hex
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="trial.wav"\r\n'
                'Content-Type: audio/wav\r\n\r\n').encode('ascii')+path.read_bytes()+f'\r\n--{boundary}--\r\n'.encode('ascii')
        request = urllib.request.Request(self.url+'/speech_to_text', data=body,
                                        headers={'Content-Type': 'multipart/form-data; boundary='+boundary})
        started = time.perf_counter()
        try:
            with self.opener.open(request, timeout=90) as response:
                status, payload = response.status, json.load(response)
        except urllib.error.HTTPError as error:
            status, payload = error.code, json.load(error)
        elapsed = time.perf_counter()-started
        return dict(**recognition_check(reference, payload.get('text', '')),
                    http_status=status, success=bool(payload.get('success')),
                    seconds=round(elapsed, 3))


class Monitor:
    def __init__(self, backend, torch):
        self.backend, self.torch = backend, torch
        self.stop = threading.Event()
        self.health, self.memory, self.errors = [], [], []
        self.worker = threading.Thread(target=self.run, daemon=True)

    def run(self):
        while not self.stop.is_set():
            try:
                _, elapsed = self.backend.get('/health', timeout=2)
                self.health.append(elapsed)
            except Exception as error:
                self.errors.append(type(error).__name__)
            free, total = self.torch.cuda.mem_get_info()
            self.memory.append((total-free)/2**30)
            self.stop.wait(.3)

    def __enter__(self):
        self.worker.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.worker.join(timeout=3)

    def report(self):
        ordered = sorted(self.health)
        p95 = ordered[min(len(ordered)-1, int(.95*len(ordered)))] if ordered else None
        return dict(health_requests=len(ordered), health_errors=self.errors,
                    health_p95_seconds=round(p95, 3) if p95 is not None else None,
                    gpu_observed_used_peak_gib=round(max(self.memory), 3) if self.memory else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/voice-base')
    parser.add_argument('--reference', type=Path, default=ROOT/'reports/voice-design/reference/reference.json')
    parser.add_argument('--backend-url', default='http://127.0.0.1:8000')
    parser.add_argument('--seed', type=int, default=20261006)
    parser.add_argument('--cpu-threads', type=int, default=4)
    parser.add_argument('--greedy-control', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.cpu_threads <= 16:
        raise ValueError('CPU threads must be between 1 and 16')
    args.output.mkdir(parents=True, exist_ok=True)
    backend = Backend(args.backend_url)
    backend.get('/health')
    device_settings, _ = backend.get('/settings/device')
    reference = json.loads(args.reference.read_text(encoding='utf-8'))
    reference_audio = args.reference.parent/'scott-reference.wav'
    if hashlib.sha256(reference_audio.read_bytes()).hexdigest() != reference['sha256']:
        raise ValueError('Selected reference hash mismatch')
    import torch
    from qwen_tts import Qwen3TTSModel
    if not torch.cuda.is_available():
        raise RuntimeError('This benchmark requires CUDA')
    torch.set_num_threads(args.cpu_threads)
    model_dir = HERE/'models/base'
    manifest = json.loads((model_dir/'scott-model.json').read_text(encoding='utf-8'))
    started = time.perf_counter()
    model = Qwen3TTSModel.from_pretrained(str(model_dir), device_map='cuda',
               dtype=torch.bfloat16, attn_implementation='sdpa', local_files_only=True)
    torch.cuda.synchronize()
    loaded = time.perf_counter()-started
    started = time.perf_counter()
    prompt = model.create_voice_clone_prompt(ref_audio=str(reference_audio),
               ref_text=reference['reference_text'], x_vector_only_mode=False)
    torch.cuda.synchronize()
    prompt_seconds = time.perf_counter()-started
    result = dict(model=manifest, reference_sha256=reference['sha256'], profile=reference['profile'],
                  seed=args.seed, cpu_threads=args.cpu_threads, attention='sdpa', dtype='bfloat16',
                  torch=torch.__version__, gpu=torch.cuda.get_device_name(),
                  load_seconds=round(loaded,3), prompt_seconds=round(prompt_seconds,3),
                  backend_device=device_settings['engines']['whisper'],
                  results=[], concurrent=[], note='SDK returns complete WAVs; timings measure full synthesis, not first audio.')

    def generate(case, suffix='', greedy=False):
        torch.manual_seed(args.seed)
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()
        started = time.perf_counter()
        options = dict(max_new_tokens=768)
        if greedy:
            options.update(do_sample=False, subtalker_dosample=False)
        else:
            options.update(temperature=.7, top_p=.95, subtalker_temperature=.7)
        with torch.inference_mode():
            waves, rate = model.generate_voice_clone(text=prepare_text(case['text']), language='Russian',
                           voice_clone_prompt=prompt, non_streaming_mode=False,
                           **options)
        torch.cuda.synchronize()
        elapsed = time.perf_counter()-started
        path = args.output/f'base-{case["id"]}{suffix}.wav'
        metrics = write_audio(waves[0], rate, path)
        return dict(**case, **metrics, prepared=prepare_text(case['text']),
                    generation_mode='greedy' if greedy else 'sampling',
                    synthesis_seconds=round(elapsed,3), real_time_factor=round(elapsed/metrics['seconds'],3),
                    vram_allocated_peak_gib=round(torch.cuda.max_memory_allocated()/2**30,3))

    print(json.dumps(dict(phase='warmup', loaded_seconds=result['load_seconds'], prompt_seconds=result['prompt_seconds'])), flush=True)
    result['warmup'] = generate(dict(id='warmup', title='Прогрев', text='Здравствуйте. Всё готово к работе.'))
    save_json(args.output/'base.json', result)
    with Monitor(backend, torch) as monitor:
        for case in cases():
            print(json.dumps(dict(phase='synthesizing', case=case['id'])), flush=True)
            row = generate(case)
            row['recognition'] = backend.transcribe(args.output/row['audio'], row['text'])
            result['results'].append(row)
            save_json(args.output/'base.json', result)
            print(json.dumps(row, ensure_ascii=False), flush=True)
        # Measure whether removing sampling helps this Windows GPU path.
        # Keep this alternative separate until diction and character are reviewed.
        if args.greedy_control:
            print(json.dumps(dict(phase='greedy_control')), flush=True)
            control = generate(cases()[0], '-greedy', greedy=True)
            control['recognition'] = backend.transcribe(args.output/control['audio'], control['text'])
            result['greedy_control'] = control
            save_json(args.output/'base.json', result)
        silero = json.loads((args.output/'silero.json').read_text(encoding='utf-8'))
        for row in silero['results']:
            row['recognition'] = backend.transcribe(args.output/row['audio'], row['text'])
        save_json(args.output/'silero.json', silero)
        # The API only transcribes synthetic files; it never asks Scott to act.
        for case in [item for item in cases() if item['id'] in ('status', 'technical')]:
            print(json.dumps(dict(phase='concurrent', case=case['id'])), flush=True)
            with ThreadPoolExecutor(max_workers=1) as pool:
                task = pool.submit(backend.transcribe, reference_audio, reference['reference_text'])
                row = generate(case, '-concurrent')
                row['overlapping_recognition'] = task.result()
            row['recognition'] = backend.transcribe(args.output/row['audio'], row['text'])
            result['concurrent'].append(row)
            save_json(args.output/'base.json', result)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    result['monitor'] = monitor.report()
    result['summary'] = dict(mean_rtf=round(statistics.mean(row['real_time_factor'] for row in result['results']),3),
                             zero_wer=sum(row['recognition']['success'] and row['recognition']['word_error_rate']==0 for row in result['results']),
                             cases=len(result['results']))
    backend.get('/health')
    save_json(args.output/'base.json', result)
    print(json.dumps(result['summary']), flush=True)


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    main()
