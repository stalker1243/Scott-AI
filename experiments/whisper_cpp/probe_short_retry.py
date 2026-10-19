"""Measure one padded retry of native short loops; never enable the policy."""
import argparse
import json
import math
from pathlib import Path
import shutil

from benchmark import ROOT, Native, isolated, write_json, sha


def native_score(result):
    # A native text-token mean, NOT Python's avg_logprob or correctness probability.
    segments = result.get('segments') or []
    values = [s.get('mean_text_token_logprob') for s in segments]
    silence = [s.get('no_speech_prob') for s in segments]
    if not values or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in values + silence):
        return None
    if max(silence) > .6:
        return None
    return sum(values) / len(values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('worker', 'model', 'corpus', 'baseline', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--device', choices=('cpu', 'vulkan'), default='vulkan')
    args = parser.parse_args()
    for name in ('worker', 'model', 'corpus', 'baseline', 'output'):
        value = getattr(args, name).resolve()
        if not value.is_relative_to(ROOT / 'reports'):
            parser.error('Use experimental files inside reports')
        setattr(args, name, value)
    if args.output.exists():
        parser.error('Choose a new output directory')
    args.output.mkdir(parents=True)
    baseline = json.loads(args.baseline.read_text(encoding='utf-8'))
    if baseline.get('engine') != 'cpp' or baseline.get('model') != 'turbo':
        parser.error('A native turbo baseline is required')
    if baseline['device'] != args.device or baseline['model_sha256'] != sha(args.model) or baseline['worker_sha256'] != sha(args.worker):
        parser.error('Use the same model, worker and device as the baseline')
    args.threads, args.fallback, args.owner_watch = 8, .2, True
    args.beam_size = baseline['ready']['decoder_options']['beam_size']
    options = baseline['ready']['decoder_options']
    args.prompt_space = options['prompt_space']
    args.no_flash_attn = not options['flash_attn']
    args.no_timestamps = options['no_timestamps']
    fixtures = args.output / 'fixtures'
    fixtures.mkdir()
    shutil.copy2(args.corpus / 'prompt.txt', fixtures / 'prompt.txt')
    isolated(args.corpus / 'source' / 'backend')
    import speech_to_text as stt
    rows = []
    worker = Native(args, fixtures, args.output)
    try:
        for sample in baseline['rows']:
            # The original decoder stays authoritative unless this narrow gate fires.
            first = sample.get('native_result') or {}
            text = first.get('text', '').strip()
            original = args.corpus / sample['pcm']
            if not original.resolve().is_relative_to(args.corpus):
                raise ValueError('PCM outside corpus')
            if sha(original) != sample['sha256']:
                raise ValueError('PCM changed since baseline')
            eligible = (original.stat().st_size <= 32000 * 4 and stt.repeated_word(text)
                        and native_score(first) is not None)
            if not eligible:
                continue
            padded = f"{sample['id']:03}-padded.f32"
            # Exactly 300 ms at each side; immutable original PCM is untouched.
            (fixtures / padded).write_bytes(bytes(4800 * 4) + original.read_bytes() + bytes(4800 * 4))
            retry = worker.transcribe(dict(id=sample['id'], pcm=padded))
            if retry.get('error'):
                raise RuntimeError('Retry decode failed')
            candidate = retry.get('text', '').strip()
            score = native_score(retry)
            accepted = bool(candidate and not stt.repeated_word(candidate)
                and not stt.looks_like_hallucination(candidate)
                and score is not None and score >= native_score(first))
            rows.append(dict(id=sample['id'], reference=sample['reference'],
                clip_seconds=sample['clip_seconds'], first=first, retry=retry,
                accepted=accepted, selected_text=candidate if accepted else text))
            write_json(args.output / 'partial.json', rows)
        write_json(args.output / 'result.json', dict(ready=worker.ready, rows=rows,
            eligible=len(rows), accepted=sum(r['accepted'] for r in rows),
            enabled=False, microphone_used=False, playback_used=False, commands_executed=False,
            score_definition='mean of native segment text-token mean log probabilities'))
        print(json.dumps(dict(eligible=len(rows), accepted=sum(r['accepted'] for r in rows))))
    finally:
        worker.close()


if __name__ == '__main__':
    main()
