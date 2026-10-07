"""Create local voice comparisons and optionally transcribe them; no playback."""
import argparse
import json
import math
import re
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

import silero_tts
import speech_text
import voice_character

SAMPLE = ('Скотт на связи. Всё в порядке. Я проверю детали и помогу с задачей. '
          'Яркость — 40 процентов. Запущено 5 процессов. '
          'Программное обеспечение обновлено. Проверьте API Token и файл PDF.')


def words(text):
    normalized = speech_text.prepare_for_speech(text, accents=False).lower().replace('ё', 'е')
    return re.findall(r'[а-я]+', normalized)


def word_error_rate(reference, hypothesis):
    previous = list(range(len(hypothesis) + 1))
    for i, left in enumerate(reference, 1):
        current = [i]
        for j, right in enumerate(hypothesis, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (left != right)))
        previous = current
    return previous[-1] / max(1, len(reference))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recognize', action='store_true')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent.parent / 'reports/voice-profile')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    recognizer = None
    if args.recognize:
        import speech_to_text
        import device_settings
        speech_to_text.ENGINE_CHOICE = 'openai'
        recognizer = speech_to_text.Recognizer('small', device_settings.resolve_device('whisper'))
        recognizer.load()
    results = []
    text = speech_text.prepare_for_speech(SAMPLE)
    for voice in ('eugene', 'aidar'):
        raw_path = args.output / f'{voice}-natural.wav'
        started = time.perf_counter()
        if not silero_tts.synthesize(text, str(raw_path), voice):
            raise RuntimeError('Local synthesis failed; no cloud fallback is used')
        synthesis_seconds = time.perf_counter() - started
        audio, rate = sf.read(raw_path, dtype='float32')
        for character in ('natural', 'calm'):
            processed = voice_character.apply(audio, rate, character)
            path = args.output / f'{voice}-{character}.wav'
            sf.write(path, processed, rate, subtype='PCM_16')
            row = dict(voice=voice, character=character, audio=str(path.resolve()),
                       seconds=round(len(processed) / rate, 2), sample_rate=rate,
                       peak=round(float(np.max(np.abs(processed))), 4),
                       rms=round(float(np.sqrt(np.mean(processed ** 2))), 4),
                       finite=bool(np.isfinite(processed).all()),
                       synthesis_seconds=round(synthesis_seconds, 3))
            if recognizer:
                factor = math.gcd(rate, 16000)
                heard = recognizer.transcribe(resample_poly(processed, 16000 // factor, rate // factor).astype(np.float32))
                row.update(heard=heard, word_error_rate=round(word_error_rate(words(SAMPLE), words(heard)), 4))
            results.append(row)
    result = dict(reference=SAMPLE, prepared=text, results=results,
                  note='Synthetic sample only; recognition does not measure vocal softness or word stress.')
    (args.output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if all(row['finite'] and row['peak'] <= 1 and row['seconds'] > 1 for row in results) else 1


if __name__ == '__main__':
    import sys
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    raise SystemExit(main())
