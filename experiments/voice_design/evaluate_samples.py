"""Transcribe synthetic voice samples locally; never execute their contents."""
from pathlib import Path
import argparse
import json
import re
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def word_error_rate(reference, hypothesis):
    previous = list(range(len(hypothesis)+1))
    for i, left in enumerate(reference, 1):
        current = [i]
        for j, right in enumerate(hypothesis, 1):
            current.append(min(current[-1]+1, previous[j]+1, previous[j-1]+(left != right)))
        previous = current
    return previous[-1]/max(1, len(reference))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/voice-design')
    parser.add_argument('--model', default='turbo')
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT/'backend'))
    import speech_text
    import speech_to_text
    import torch
    speech_to_text.ENGINE_CHOICE = 'openai'
    recognizer = speech_to_text.Recognizer(args.model, 'cuda' if torch.cuda.is_available() else 'cpu')
    source = json.loads((args.output/'samples.json').read_text(encoding='utf-8'))
    def words(text):
        text = speech_text.prepare_for_speech(text, accents=False).casefold().replace('ё', 'е')
        return re.findall(r'[а-я]+', text)
    reference = words(source['prepared'])
    recognizer.load()
    result = dict(model=args.model, reference=source['prepared'], results=[],
                  note='Automatic transcription checks words, not voice character or word stress.')
    samples = list(source['results'])
    baseline = args.output/'baseline.json'
    if baseline.exists():
        samples.append(json.loads(baseline.read_text(encoding='utf-8')))
    for row in samples:
        started = time.perf_counter()
        heard = recognizer.transcribe(str(args.output/row['audio']))
        check = dict(profile=row['profile'], heard=heard,
                     word_error_rate=round(word_error_rate(reference, words(heard)), 4),
                     recognition_seconds=round(time.perf_counter()-started, 3))
        result['results'].append(check)
        print(json.dumps(check, ensure_ascii=False), flush=True)
    (args.output/'recognition.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    main()
