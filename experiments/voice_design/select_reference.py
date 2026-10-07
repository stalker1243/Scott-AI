"""Preserve a chosen synthetic voice sample for later local Qwen Base trials."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import wave

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', choices=['soft', 'neutral', 'firm'])
    parser.add_argument('--output', type=Path, default=ROOT/'reports/voice-design')
    args = parser.parse_args()
    samples = json.loads((args.output/'samples.json').read_text(encoding='utf-8'))
    row = next(item for item in samples['results'] if item['profile'] == args.profile)
    source = args.output/row['audio']
    if not source.resolve().is_relative_to(args.output.resolve()):
        raise ValueError('Sample path escaped the output directory')
    with wave.open(str(source), 'rb') as audio:
        if audio.getnchannels() != 1 or audio.getsampwidth() != 2:
            raise ValueError('Reference must be mono PCM16')
        rate = audio.getframerate()
        frames = audio.getnframes()
        if frames == 0 or rate != row['sample_rate']:
            raise ValueError('Reference format does not match sample metadata')
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    directory = args.output/'reference'
    directory.mkdir(parents=True, exist_ok=True)
    target = directory/'scott-reference.wav'
    temporary = target.with_suffix('.wav.tmp')
    shutil.copyfile(source, temporary)
    if hashlib.sha256(temporary.read_bytes()).hexdigest() != checksum:
        raise ValueError('Reference copy failed checksum verification')
    temporary.replace(target)
    selection = dict(profile=args.profile, title=row['title'],
                     description=row['description'], source_audio=row['audio'],
                     reference_audio='reference/scott-reference.wav',
                     sha256=checksum, reference_text=samples['prepared'],
                     sample_rate=rate, seconds=round(frames/rate, 3),
                     model=samples['model'], seed=samples['seed'],
                     instruct=row['instruct'])
    payload = json.dumps(selection, ensure_ascii=False, indent=2)
    (directory/'reference.json').write_text(payload, encoding='utf-8')
    (args.output/'selection.json').write_text(payload, encoding='utf-8')
    # Keep the chosen character in source control; audio remains a local artifact.
    preference = dict(profile=args.profile, title=row['title'],
                      reference_sha256=checksum, seed=samples['seed'],
                      model=samples['model']['model'], revision=samples['model']['revision'])
    preference_file = HERE/'selected_voice.json'
    if preference_file.exists():
        previous = json.loads(preference_file.read_text(encoding='utf-8'))
        if previous.get('reference_sha256') == checksum and previous.get('profile') == args.profile and 'base' in previous:
            preference['base'] = previous['base']
    preference_file.write_text(json.dumps(preference, ensure_ascii=False, indent=2), encoding='utf-8')
    print(str(target.resolve()))


if __name__ == '__main__':
    main()
