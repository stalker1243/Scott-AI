"""Compare Whisper on synthetic commands; no microphone or command execution.

    py -3.13 backend/check_recognition.py --models small --compare-baseline

Models may be downloaded on the first run. Reports contain synthetic text only.
"""
from __future__ import annotations

import argparse
import gc
import json
import re
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from accuracy_voice import _озвучить, _same_decision
from check_voice_profile import word_error_rate
import speech_text
import speech_to_text

# Separate from the intent test corpus. Search terms and project names are
# deliberately kept intact; the recognizer must not rewrite them into commands.
PHRASES = (
    'Скотт, открой калькулятор',
    'Скотт, установи громкость на сорок пять процентов',
    'Скотт, найди в интернете информацию о спутниках Юпитера',
    'Скотт, создай папку документы',
    'Скотт, какая нагрузка на процессор',
    'Скотт, выбери голос Евгения',
    'Скотт, выключи озвучку',
    'Скотт, говори немного тише',
    'Скотт, запомни, мой любимый цвет бирюзовый',
    'Скотт, напомни через десять минут проверить духовку',
    'Скотт, расскажи о северном сиянии',
    'Скотт, поставь яркость на шестьдесят процентов',
    'Скотт, открой браузер',
    'Скотт, покажи список проектов',
    'Скотт, измени характер голоса на спокойный',
    'Скотт, найди рецепт грибного супа',
)


def words(text):
    text = speech_text.prepare_for_speech(text, accents=False).casefold().replace('ё', 'е')
    return re.findall(r'\w+', text)


def variants(audio, seed):
    rng = np.random.default_rng(seed)
    # 15 dB SNR, fixed random seed, half a second of padding on each side.
    noise = rng.normal(0, np.sqrt(np.mean(audio ** 2)) / (10 ** (15 / 20)), len(audio))
    pad = np.zeros(8000, dtype=np.float32)
    return {'clean': audio, 'quiet': audio * 0.04,
            'noise_15db': np.concatenate((pad, np.clip(audio + noise, -1, 1), pad)).astype(np.float32)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', nargs='+', default=['small'])
    parser.add_argument('--compare-baseline', action='store_true')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent.parent / 'reports/recognition')
    parser.add_argument('--download-root', type=Path, default=None)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    import device_settings
    import understanding
    from fast_intent import get_fast_intent_engine
    from command_parser import get_command_parser
    from question_answerer import get_question_answerer
    from voice_name_trigger import check_voice_trigger
    import whisper
    import torch

    engines = dict(intent_engine=get_fast_intent_engine(), parser=get_command_parser(), answerer=get_question_answerer())

    def decision(text):
        trigger = check_voice_trigger(text)
        return (trigger.has_trigger, understanding.understand(trigger.command_text, **engines))

    samples = []
    for i, text in enumerate(PHRASES):
        voice = ('aidar', 'eugene')[i % 2]
        path = args.output / f'{i:02}-{voice}.wav'
        if path.exists():
            audio, rate = sf.read(path, dtype='float32')
            if rate != 16000:
                from scipy.signal import resample_poly
                import math
                factor = math.gcd(rate, 16000)
                audio = resample_poly(audio, 16000 // factor, rate // factor).astype(np.float32)
        else:
            audio = _озвучить(text, str(path), voice)
        if audio is None:
            raise RuntimeError('Local synthesis failed; no cloud fallback is used')
        expected = decision(text)
        for condition, wave in variants(audio, i).items():
            samples.append((text, voice, condition, wave, expected))
    all_results = []
    for name in args.models:
        device = device_settings.resolve_device('whisper')
        # Reuse existing small checkpoints; larger comparisons can keep their
        # download inside the workspace instead of changing the user's cache.
        cached = Path.home() / '.cache/whisper' / f'{name}.pt'
        options = {'download_root': str(args.download_root)} if args.download_root and not cached.exists() else {}
        raw = whisper.load_model(name, device=device, **options)
        recognizer = speech_to_text.Recognizer(name, device)
        recognizer.engine = 'openai-whisper'
        recognizer._model = raw
        for mode in (['baseline', 'current'] if args.compare_baseline else ['current']):
            rows = []
            for text, voice, condition, audio, expected in samples:
                started = time.perf_counter()
                if mode == 'baseline':
                    heard = raw.transcribe(audio, language='ru', fp16=device == 'cuda',
                                           initial_prompt=speech_to_text._подсказка(),
                                           temperature=speech_to_text.TEMPERATURES)['text'].strip()
                else:
                    heard = recognizer.transcribe(audio)
                duration = time.perf_counter() - started
                actual = decision(heard) if heard else (False, None)
                rows.append(dict(reference=text, heard=heard, voice=voice, condition=condition,
                                 wer=round(word_error_rate(words(text), words(heard)), 4),
                                 routing_correct=expected[0] == actual[0] and _same_decision(expected[1], actual[1]),
                                 seconds=round(duration, 3)))
            backgrounds = {'short_silence': np.zeros(16000, np.float32),
                           'silence': np.zeros(40000, np.float32),
                           'noise': np.random.default_rng(42).normal(0, .003, 48000).astype(np.float32)}
            # The baseline used VAD on long recordings, so keep that check.
            empty = {key: (raw.transcribe(wave, language='ru', fp16=device == 'cuda',
                          initial_prompt=speech_to_text._подсказка(), temperature=speech_to_text.TEMPERATURES)['text'].strip()
                          if mode == 'baseline' and recognizer._есть_речь(wave) else
                          '' if mode == 'baseline' else recognizer.transcribe(wave))
                     for key, wave in backgrounds.items()}
            summary = {}
            for condition in ('clean', 'quiet', 'noise_15db'):
                subset = [row for row in rows if row['condition'] == condition]
                summary[condition] = dict(count=len(subset), routing_correct=sum(r['routing_correct'] for r in subset),
                    mean_wer=round(float(np.mean([r['wer'] for r in subset])), 4),
                    mean_seconds=round(float(np.mean([r['seconds'] for r in subset])), 3))
            result = dict(model=name, engine=recognizer.engine, device=device, mode=mode,
                          summary=summary, background_transcripts=empty, rows=rows)
            all_results.append(result)
            (args.output / 'result.json').write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({k:v for k,v in result.items() if k != 'rows'}, ensure_ascii=False), flush=True)
        recognizer._model = None
        del raw, recognizer
        gc.collect()
        if device == 'cuda':
            torch.cuda.empty_cache()
    return 0


if __name__ == '__main__':
    import sys
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    raise SystemExit(main())
