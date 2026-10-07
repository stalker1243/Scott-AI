"""Measure Scott's existing voice on the same cases, with a separate warmup."""
import argparse
import sys
import time
from pathlib import Path

from trial_utils import ROOT, cases, save_json, write_audio


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/voice-base')
    parser.add_argument('--cpu-threads', type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.cpu_threads <= 16:
        raise ValueError('CPU threads must be between 1 and 16')
    args.output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT/'backend'))
    import silero_tts
    import speech_text
    import voice_character
    import soundfile as sf
    import torch
    torch.set_num_threads(args.cpu_threads)
    started = time.perf_counter()
    silero_tts.get_model()
    loaded = time.perf_counter()-started
    warmup = args.output/'silero-warmup.wav'
    started = time.perf_counter()
    if not silero_tts.synthesize('Здравствуйте. Всё готово к работе.', str(warmup), 'eugene'):
        raise RuntimeError('Silero warmup failed')
    warmup_seconds = time.perf_counter()-started
    # CUDA/JIT can initialize different kernels for different sentence lengths.
    # Prime every tested shape before comparing the measured pass.
    started = time.perf_counter()
    for case in cases():
        if not silero_tts.synthesize(speech_text.prepare_for_speech(case['text']), str(warmup), 'eugene'):
            raise RuntimeError('Silero case warmup failed: '+case['id'])
    if silero_tts._model_device == 'cuda':
        torch.cuda.synchronize()
    priming_seconds = time.perf_counter()-started
    result = dict(voice='eugene', character='calm', device=silero_tts._model_device,
                  cpu_threads=args.cpu_threads, load_seconds=round(loaded, 3),
                  warmup_seconds=round(warmup_seconds, 3), priming_seconds=round(priming_seconds, 3), results=[])
    for case in cases():
        path = args.output/f'silero-{case["id"]}.wav'
        if silero_tts._model_device == 'cuda':
            torch.cuda.synchronize()
        started = time.perf_counter()
        if not silero_tts.synthesize(speech_text.prepare_for_speech(case['text']), str(path), 'eugene'):
            raise RuntimeError('Silero synthesis failed: '+case['id'])
        audio, rate = sf.read(path, dtype='float32')
        audio = voice_character.apply(audio, rate, 'calm')
        metrics = write_audio(audio, rate, path)
        if silero_tts._model_device == 'cuda':
            torch.cuda.synchronize()
        elapsed = time.perf_counter()-started
        row = dict(**case, **metrics, synthesis_seconds=round(elapsed, 3),
                   real_time_factor=round(elapsed/metrics['seconds'], 3))
        result['results'].append(row)
        save_json(args.output/'silero.json', result)
        print(str(dict(case=case['id'], synthesis_seconds=row['synthesis_seconds'])), flush=True)


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    main()
