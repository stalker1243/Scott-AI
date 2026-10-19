"""Exercise Unicode model/root/prompt/PCM paths with the real saved-audio worker."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from benchmark import ROOT, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('worker', 'model', 'corpus', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--observe', action='store_true', help='Record the unfixed worker without requiring success')
    args = parser.parse_args()
    for name in ('worker', 'model', 'corpus', 'output'):
        setattr(args, name, getattr(args, name).resolve())
    if not args.output.is_relative_to(ROOT/'reports') or args.output.exists():
        parser.error('Choose a new report directory')
    if not args.model.is_relative_to(ROOT/'reports'):
        parser.error('Use an experimental model inside reports')
    args.output.mkdir(parents=True)
    plain = args.output/'plain'
    unicode_root = args.output/'Проверка 中文 🎙 с пробелами'
    plain.mkdir(); unicode_root.mkdir()
    for folder in (plain, unicode_root):
        shutil.copy2(args.corpus/'prompt.txt', folder/'prompt.txt')
        shutil.copy2(args.corpus/'prompt.txt', folder/'Подсказка 中文 🎙.txt')
        shutil.copy2(args.corpus/'000.f32', folder/'valid.f32')
        shutil.copy2(args.corpus/'000.f32', folder/'Фраза 中文 🎙.f32')
    model_alias = plain/'Модель 中文 🎙.bin'
    # The alias shares immutable experimental weights; this test never writes to it.
    os.link(args.model, model_alias)
    cases = [
        ('model', model_alias, plain, plain/'prompt.txt', 'valid.f32'),
        ('root', args.model, unicode_root, plain/'prompt.txt', 'valid.f32'),
        ('prompt', args.model, plain, plain/'Подсказка 中文 🎙.txt', 'valid.f32'),
        ('relative_pcm', args.model, plain, plain/'prompt.txt', 'Фраза 中文 🎙.f32'),
        ('all', model_alias, unicode_root, unicode_root/'Подсказка 中文 🎙.txt', 'Фраза 中文 🎙.f32'),
    ]
    rows = []
    for name, model, folder, prompt, pcm in cases:
        with (args.output/f'{name}.log').open('w', encoding='utf-8') as log:
            result = subprocess.run([str(args.worker), str(model), str(folder), 'cpu', '8', str(prompt), '0'],
                input=json.dumps(dict(id=1, pcm=pcm))+'\n', encoding='utf-8', errors='replace',
                stdout=subprocess.PIPE, stderr=log, timeout=40,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        ready = next((r for r in replies if r.get('event') == 'ready'), {})
        decoded = next((r for r in replies if r.get('event') == 'result'), {})
        rows.append(dict(name=name, exit_code=result.returncode, ready=bool(ready),
            text=decoded.get('text'), error=decoded.get('error'),
            passed=result.returncode == 0 and bool(ready) and bool(decoded.get('text')) and not decoded.get('error')))
        write_json(args.output/'partial.json', rows)
    successes = [r['text'] for r in rows if r['passed']]
    same_text = bool(successes) and len(set(successes)) == 1
    write_json(args.output/'result.json', dict(checks=rows, same_text=same_text, observation_only=args.observe,
        microphone_used=False, playback_used=False, commands_executed=False))
    print(json.dumps(dict(passed=sum(r['passed'] for r in rows), count=len(rows), same_text=same_text)))
    if not args.observe:
        assert all(r['passed'] for r in rows) and same_text


if __name__ == '__main__':
    main()
