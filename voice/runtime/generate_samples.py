"""Generate three original Russian male voices; no playback or app imports."""
from pathlib import Path
import argparse
import importlib.util
import json
import os
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
os.environ['HF_HOME'] = str(HERE / 'models/cache')
os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['PYTHONUTF8'] = '1'

REFERENCE = ('Здравствуйте. Всё в порядке. Я проверю детали и помогу с задачей. '
             'Яркость экрана — 40 процентов. Запущено 5 процессов. '
             'Программное обеспечение обновлено. Проверьте API Token и файл PDF.')


def prepare_text(text):
    # Reuse only the pure text formatter, without importing the running app.
    spec = importlib.util.spec_from_file_location('scott_speech_text', ROOT/'backend/speech_text.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Silero's '+' accent notation is not an instruction format for Qwen.
    return module.prepare_for_speech(text, accents=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/voice-design')
    parser.add_argument('--profiles', nargs='+', choices=['soft', 'neutral', 'firm'], default=['soft', 'neutral', 'firm'])
    parser.add_argument('--seed', type=int, default=20261006)
    parser.add_argument('--device', choices=['cuda', 'cpu'], default='cuda')
    parser.add_argument('--attention', choices=['sdpa', 'eager'], default='sdpa')
    parser.add_argument('--cpu-threads', type=int)
    parser.add_argument('--warmup', action='store_true')
    args = parser.parse_args()
    if args.cpu_threads is not None and not 1 <= args.cpu_threads <= 16:
        raise ValueError('CPU threads must be between 1 and 16')
    import numpy as np
    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel
    if args.cpu_threads is not None:
        torch.set_num_threads(args.cpu_threads)
    if args.device == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable; pass --device cpu explicitly for a slower experiment.')
    args.output.mkdir(parents=True, exist_ok=True)
    source = HERE/'models/design'
    manifest = json.loads((source/'scott-model.json').read_text(encoding='utf-8'))
    profiles = json.loads((HERE/'profiles.json').read_text(encoding='utf-8'))
    text = prepare_text(REFERENCE)
    print(json.dumps(dict(phase='loading', model=manifest['model'])), flush=True)
    started = time.perf_counter()
    model = Qwen3TTSModel.from_pretrained(str(source), device_map=args.device,
                                        dtype=torch.bfloat16 if args.device == 'cuda' else torch.float32,
                                        attn_implementation=args.attention, local_files_only=True)
    if args.device == 'cuda':
        torch.cuda.synchronize()
    load_seconds = time.perf_counter()-started
    warmup_seconds = None
    if args.warmup:
        started = time.perf_counter()
        with torch.inference_mode():
            model.generate_voice_design(text='Здравствуйте. Всё готово к работе.', language='Russian',
                  instruct=profiles[args.profiles[0]]['instruct'], max_new_tokens=256,
                  temperature=.7, top_p=.95, subtalker_temperature=.7)
        if args.device == 'cuda':
            torch.cuda.synchronize()
        warmup_seconds = round(time.perf_counter()-started, 3)
    result = dict(model=manifest, reference=REFERENCE, prepared=text, seed=args.seed,
                  device=args.device, attention=args.attention, torch=torch.__version__,
                  gpu=torch.cuda.get_device_name(0) if args.device == 'cuda' else None,
                  load_seconds=round(load_seconds, 3), cpu_threads=torch.get_num_threads(),
                  warmup_seconds=warmup_seconds, results=[])
    report = args.output/'samples.json'
    for name in args.profiles:
        print(json.dumps(dict(phase='synthesizing', profile=name)), flush=True)
        torch.manual_seed(args.seed)
        if args.device == 'cuda':
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()
        started = time.perf_counter()
        with torch.inference_mode():
            wavs, rate = model.generate_voice_design(text=text, language='Russian',
                        instruct=profiles[name]['instruct'], max_new_tokens=768,
                        temperature=0.7, top_p=0.95, subtalker_temperature=0.7)
        if args.device == 'cuda':
            torch.cuda.synchronize()
        elapsed = time.perf_counter()-started
        audio = np.asarray(wavs[0], dtype=np.float32)
        if audio.ndim != 1 or audio.size == 0 or not np.isfinite(audio).all():
            raise ValueError('Invalid synthesized audio for '+name)
        peak = float(np.max(np.abs(audio)))
        rms = float(np.sqrt(np.mean(audio.astype(np.float64)**2)))
        if peak < 1e-5:
            raise ValueError('Silent synthesized audio for '+name)
        # Match audition loudness, while preserving timbre and timing.
        gain = min(4.0, 0.065/max(rms, 1e-6), 0.95/peak)
        audio *= gain
        path = args.output/f'scott-{name}.wav'
        sf.write(path, audio, rate, subtype='PCM_16')
        seconds = len(audio)/rate
        row = dict(profile=name, **profiles[name], audio=path.name,
                   seconds=round(seconds, 3), sample_rate=rate,
                   synthesis_seconds=round(elapsed, 3), real_time_factor=round(elapsed/seconds, 3),
                   gain=round(gain, 4), peak=round(float(np.max(np.abs(audio))), 4),
                   rms=round(float(np.sqrt(np.mean(audio.astype(np.float64)**2))), 4),
                   vram_peak_gib=round(torch.cuda.max_memory_allocated()/2**30, 3) if args.device == 'cuda' else None)
        result['results'].append(row)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(row, ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    import sys
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    raise SystemExit(main())
