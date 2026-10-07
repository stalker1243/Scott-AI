"""Measure cold first-chunk latency offline; never play audio or execute speech."""
from dataclasses import replace
from pathlib import Path
import argparse
import json
import re
import shutil
import sys
import textwrap
import time

from trial_utils import ROOT, save_json
sys.path.insert(0, str(ROOT/'backend'))
from scott_voice_engine import default_config, speech_chunks
from scott_voice_process import ScottVoiceProcess, checksum
from speech_text import prepare_for_speech, split_for_speech

TEXT = ('Проверка завершена, все необходимые настройки сохранены, '
        'соединение с сервером восстановлено и приложение готово продолжить работу с выбранной моделью.')


def short_first(chunks):
    first, *rest = chunks
    if len(first) <= 110:
        return chunks
    # Prefer a clause boundary, keeping commas/dashes with their original words.
    boundaries = [m.end() for m in re.finditer(r'[,;:](?=\s)|\s[—–](?=\s)', first)
                  if 40 <= m.end() <= 90]
    cut = boundaries[-1] if boundaries else len(textwrap.wrap(first, width=90,
        break_long_words=False, break_on_hyphens=False)[0])
    if cut == len(first):
        return chunks
    return [first[:cut].strip(), first[cut:].strip(), *rest]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/voice-latency')
    parser.add_argument('--verify-implementation', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.verify_implementation:
        result = json.loads((args.output/'latency.json').read_text(encoding='utf-8'))
        assert speech_chunks(TEXT) == result['variants']['short_first']['chunks']
        print('Implementation matches the measured chunks.')
        return
    if (args.output/'latency.json').exists():
        raise ValueError('Choose a new --output directory to preserve previous measurements.')
    # Preserve the old control even after production speech_chunks is updated.
    before = [part for sentence in split_for_speech(prepare_for_speech(TEXT, accents=False), min_chars=120)
              for part in textwrap.wrap(sentence, width=180, break_long_words=True, break_on_hyphens=False)]
    variants = dict(original=before, short_first=short_first(before))
    assert ' '.join(variants['short_first']).split() == ' '.join(before).split()
    original = default_config()
    reference = original.reference_json.with_name('scott-reference.wav')
    accepted_sha = json.loads(original.reference_json.read_text(encoding='utf-8'))['sha256']
    assert checksum(reference) == accepted_sha
    report = dict(text=TEXT, reference_sha256=accepted_sha, device=original.device,
                  cpu_threads=original.cpu_threads, rms_norm=original.rms_norm, variants={})
    for name, chunks in variants.items():
        config = replace(original, cache_dir=args.output/name/'cache')
        outputs = []
        with ScottVoiceProcess(config, timeout=180, idle_timeout=0) as client:
            for index, chunk in enumerate(chunks):
                started = time.perf_counter()
                audio = client.synthesize(chunk, 'natural')
                elapsed = time.perf_counter()-started
                assert not audio.cached, 'Use a new report directory for a fresh measurement.'
                target = args.output/f'{name}-{index+1}.wav'
                shutil.copyfile(audio.path, target)
                outputs.append(dict(text=chunk, chars=len(chunk), audio=target.name,
                    seconds=audio.seconds, synthesis_seconds=round(elapsed,3), sha256=checksum(target)))
                print(json.dumps(dict(variant=name, chunk=index+1, chars=len(chunk), seconds=round(elapsed,3))), flush=True)
            hits = []
            for chunk in chunks:
                start = time.perf_counter()
                assert client.synthesize(chunk,'natural').cached
                hits.append(round((time.perf_counter()-start)*1000,3))
        report['variants'][name] = dict(chunks=chunks, outputs=outputs, cache_ms=hits,
            first_audio_seconds=outputs[0]['synthesis_seconds'],
            total_synthesis_seconds=round(sum(row['synthesis_seconds'] for row in outputs),3))
        save_json(args.output/'latency.json', report)
    report['first_audio_speedup'] = round(report['variants']['original']['first_audio_seconds']/
        report['variants']['short_first']['first_audio_seconds'],3)
    assert checksum(reference) == accepted_sha
    save_json(args.output/'latency.json',report)


if __name__ == '__main__':
    main()
