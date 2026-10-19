"""Observe the installed Python decoder on immutable synthetic audio only."""
import argparse
from contextlib import contextmanager
import json
import hashlib
import math
from pathlib import Path
import shutil
import sys

from benchmark import ROOT, isolated, sha, write_json


def finite(value):
    if isinstance(value, float) and not math.isfinite(value): return None
    if isinstance(value, dict): return {k: finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [finite(v) for v in value]
    return value


class Recorder:
    def __init__(self):
        self.events, self.bytes, self.omitted = [], 0, 0
    def add(self, event):
        event = finite(event)
        size = len(json.dumps(event, ensure_ascii=False, allow_nan=False).encode('utf-8'))
        if len(self.events) >= 512 or self.bytes + size > 1024 * 1024:
            self.omitted += 1
            return
        self.events.append(event)
        self.bytes += size


@contextmanager
def observe(recorder):
    import whisper.decoding as d
    originals = []
    def patch(cls, name, wrapper):
        original = getattr(cls, name)
        originals.append((cls, name, original))
        setattr(cls, name, wrapper(original))
    def main_loop(original):
        def wrapped(self, features, tokens):
            recorder.add(dict(kind='prompt', prompt=tokens[0].tolist(), eot=self.tokenizer.eot,
                timestamp_begin=self.tokenizer.timestamp_begin, sample_begin=self.sample_begin,
                temperature=self.options.temperature))
            return original(self, features, tokens)
        return wrapped
    def update(original):
        def wrapped(self, tokens, logits, scores):
            result = original(self, tokens, logits, scores)
            recorder.add(dict(kind='step', active_last_ids=result[0][:, -1].tolist(),
                completed=result[1], finished=[dict(ids=list(ids), sum_logprobs=float(score))
                    for group in self.finished_sequences for ids, score in group.items()]))
            return result
        return wrapped
    def finalize(original):
        def wrapped(self, tokens, scores):
            result = original(self, tokens, scores)
            recorder.add(dict(kind='pre_rank', candidates=[dict(ids=ids.tolist(), sum_logprobs=float(score))
                for group, group_scores in zip(*result) for ids, score in zip(group, group_scores)]))
            return result
        return wrapped
    def rank(original):
        def wrapped(self, tokens, scores):
            selected = original(self, tokens, scores)
            candidates = []
            for group, sums in zip(tokens, scores):
                entries = []
                for ids, total in zip(group, sums):
                    length = len(ids)
                    penalty = length if self.length_penalty is None else ((5 + length) / 6) ** self.length_penalty
                    entries.append(dict(ids=ids.tolist(), sum_logprobs=float(total), length=length,
                        penalty=penalty, score=float(total) / penalty if penalty else None))
                candidates.append(entries)
            recorder.add(dict(kind='post_rank', groups=candidates, selected=[int(x) for x in selected]))
            return selected
        return wrapped
    try:
        patch(d.DecodingTask, '_main_loop', main_loop)
        patch(d.BeamSearchDecoder, 'update', update)
        patch(d.BeamSearchDecoder, 'finalize', finalize)
        patch(d.MaximumLikelihoodRanker, 'rank', rank)
        yield
    finally:
        for cls, name, original in reversed(originals): setattr(cls, name, original)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('corpus', 'model', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--ids', type=int, nargs='+', required=True)
    args = parser.parse_args()
    args.corpus, args.model, args.output = (getattr(args, n).resolve() for n in ('corpus', 'model', 'output'))
    if not args.corpus.is_relative_to(ROOT / 'reports') or not args.output.is_relative_to(ROOT / 'reports') or args.output.exists():
        parser.error('Use existing experimental corpus and a new reports output')
    manifest = json.loads((args.corpus / 'manifest.json').read_text(encoding='utf-8'))
    rows = [r for r in manifest['samples'] if r['id'] in args.ids]
    args.output.mkdir(parents=True)
    checkpoint = args.output / 'model-input/large-v3-turbo.pt'
    checkpoint.parent.mkdir()
    # Copy before installing the guard; never load or mutate the working checkpoint.
    shutil.copy2(args.model, checkpoint)
    model_sha = sha(checkpoint)
    isolated(args.corpus / 'source/backend')
    import numpy as np
    import torch
    import whisper
    import speech_to_text as stt
    torch.set_num_threads(8)
    recognizer = stt.Recognizer('turbo', 'cuda')
    recognizer._model = whisper.load_model(str(checkpoint), device='cuda')
    recognizer.engine = 'openai'
    stt._подсказка = lambda: (args.corpus / 'prompt.txt').read_text(encoding='utf-8')
    tokenizer = whisper.tokenizer.get_tokenizer(multilingual=True,
        num_languages=recognizer._model.num_languages, language='ru', task='transcribe')
    results = []
    try:
        for row in rows:
            assert sha(args.corpus / row['pcm']) == row['sha256']
            raw = np.fromfile(args.corpus / row['raw'], dtype='<f4')
            normalized = stt.normalize_quiet_audio(stt.prepare_audio(raw))
            assert hashlib.sha256(normalized.astype('<f4').tobytes()).hexdigest() == row['sha256']
            # Reuse the corpus's recorded VAD decision; no hub downloads or cache writes.
            recognizer._есть_речь = lambda audio: not row['gated']
            recorder = Recorder()
            torch.manual_seed(1243)
            with observe(recorder):
                text = recognizer.transcribe(raw)
            used = set()
            for event in recorder.events:
                used.update(event.get('prompt', []))
                for candidate in event.get('candidates', []) + event.get('finished', []): used.update(candidate['ids'])
                for group in event.get('groups', []):
                    for candidate in group: used.update(candidate['ids'])
                used.update(event.get('active_last_ids', []))
            vocabulary = {str(i): tokenizer.encoding.decode_single_token_bytes(i).hex() for i in sorted(used)}
            results.append(dict(**row, heard=text, decoder_trace=dict(protocol=1,
                events=recorder.events, vocabulary_hex=vocabulary,
                complete=recorder.omitted == 0, omitted=recorder.omitted)))
            write_json(args.output / 'partial.json', results)
            print(json.dumps(dict(done=len(results), total=len(rows))), flush=True)
        write_json(args.output / 'result.json', dict(engine='python', device='cuda', rows=results,
            model_sha256=model_sha, diagnostics_only=True, microphone_used=False,
            playback_used=False, commands_executed=False, vad_precomputed=True))
    finally:
        # This one owned copy only; the original checkpoint and GGML stay untouched.
        assert checkpoint.resolve().is_relative_to(args.output)
        checkpoint.unlink()
        checkpoint.parent.rmdir()


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
