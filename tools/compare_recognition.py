"""Compare acoustic decoding on saved synthetic WAVs without executing commands."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[1]

def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1024*1024), b''): result.update(part)
    return result.hexdigest()

def read_wav(path):
    import numpy as np
    with wave.open(str(path)) as stream:
        assert stream.getnchannels() == 1 and stream.getsampwidth() == 2
        rate = stream.getframerate()
        values = np.frombuffer(stream.readframes(stream.getnframes()), dtype='<i2').astype(np.float32)/32768
    if rate != 16000:
        from scipy.signal import resample_poly
        common = math.gcd(rate, 16000)
        values = resample_poly(values, 16000//common, rate//common).astype(np.float32)
    return values

def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'): stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--model', choices=('small', 'turbo'), default='turbo')
    parser.add_argument('--methods', nargs='+', choices=('current', 'padding', 'without_prompt', 'padding_without_prompt'),
                        default=('current', 'padding', 'without_prompt', 'padding_without_prompt'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT/'reports') or output.exists():
        parser.error('Choose a new folder inside reports')
    if not args.checkpoint.is_file(): parser.error('An existing checkpoint is required')
    output.mkdir(parents=True)
    source = output/'source/backend'
    source.mkdir(parents=True)
    for path in (ROOT/'backend').glob('*.py'): shutil.copy2(path, source/path.name)
    (source.parent/'.env').write_text('WARMUP_MODELS=0\nSCOTT_SEMANTIC_MEMORY=0\n', encoding='utf-8')
    model_home = source/'data/models/whisper'
    model_home.mkdir(parents=True)
    checkpoint = model_home/('large-v3-turbo.pt' if args.model == 'turbo' else args.model+'.pt')
    original_sha = sha(args.checkpoint)
    shutil.copy2(args.checkpoint, checkpoint)
    assert sha(checkpoint) == original_sha
    sys.path.insert(0, str(source))
    sys.dont_write_bytecode = True
    os.chdir(source)
    os.environ.update(WHISPER_ENGINE='openai', WARMUP_MODELS='0', SCOTT_SEMANTIC_MEMORY='0',
                      OPENAI_API_KEY='', GROQ_API_KEY='', DEEPSEEK_API_KEY='', AI_PROVIDER='', AI_MODEL='')
    from testing_guard import install
    install([ROOT/'backend/data', ROOT/'data', ROOT/'.env', ROOT/'audio_cache'])
    try:
        import numpy as np
        import torch
        import speech_to_text
        import understanding
        import accuracy_voice
        import browser_commands
        from command_parser import CommandParser
        from fast_intent import get_fast_intent_engine
        from question_answerer import get_question_answerer
        from voice_name_trigger import check_voice_trigger
        import check_recognition
        device = args.device if args.device == 'cpu' or torch.cuda.is_available() else 'cpu'
        recognizer = speech_to_text.Recognizer(args.model, device)
        started = time.perf_counter(); recognizer.load(); load_seconds = time.perf_counter()-started
        raw = recognizer._model
        prompt = speech_to_text._подсказка()
        engines = dict(intent_engine=get_fast_intent_engine(), parser=CommandParser(), answerer=get_question_answerer())
        def decide(text):
            trigger = check_voice_trigger(text)
            if not trigger.has_trigger: return None
            command = trigger.command_text
            if command.casefold().strip(' .,!?:') == 'стоп': return understanding.Decision(kind='interrupt')
            browser = browser_commands.parse(command)
            if browser: return understanding.Decision(kind='browser', parsed=browser)
            return understanding.understand(command, **engines)
        samples = []
        trial = ROOT/'reports/voice-path/audio-trial-2'
        references = json.loads((trial/'result.json').read_text(encoding='utf-8'))['rows']
        wavs = []
        for row in references:
            path = trial/row['audio']
            samples.append(('new_tools', row['reference'], row['condition'], read_wav(path)))
            wavs.append(dict(path=str(path.relative_to(ROOT)), sha256=sha(path)))
        for index, text in enumerate(check_recognition.PHRASES):
            voice = ('aidar', 'eugene')[index % 2]
            path = ROOT/f'reports/recognition-turbo/{index:02}-{voice}.wav'
            audio = read_wav(path)
            for condition, values in check_recognition.variants(audio, index).items():
                samples.append(('previous', text, condition, values))
            wavs.append(dict(path=str(path.relative_to(ROOT)), sha256=sha(path)))
        methods = tuple(dict.fromkeys(args.methods))
        rows = []
        # Each method uses the same input, voice gate, gain, filtering and model.
        for index, (corpus, reference, condition, audio) in enumerate(samples):
            expected = decide(reference)
            assert expected is not None
            audio = speech_to_text.normalize_quiet_audio(audio)
            for method in methods:
                supplied = np.pad(audio, (4800, 4800)) if 'padding' in method else audio
                started = time.perf_counter()
                if not recognizer._есть_речь(supplied):
                    result = {'text': '', 'segments': []}
                else:
                    result = raw.transcribe(supplied, language='ru', fp16=device == 'cuda',
                        initial_prompt=None if 'without_prompt' in method else prompt,
                        temperature=speech_to_text.TEMPERATURES, beam_size=speech_to_text.BEAM_SIZE,
                        best_of=5, condition_on_previous_text=False)
                elapsed = time.perf_counter()-started
                heard = (result.get('text') or '').strip()
                if speech_to_text.looks_like_hallucination(heard): heard = ''
                actual = decide(heard)
                segments = [{key: segment.get(key) for key in
                    ('avg_logprob', 'no_speech_prob', 'compression_ratio', 'temperature')}
                    for segment in result.get('segments', [])]
                rows.append(dict(corpus=corpus, reference=reference, condition=condition, method=method,
                    heard=heard, correct=accuracy_voice._same_decision(expected, actual),
                    wer=round(check_recognition.word_error_rate(check_recognition.words(reference), check_recognition.words(heard)), 4),
                    seconds=round(elapsed, 4), segments=segments))
            print(json.dumps(dict(index=index, corpus=corpus, correct=sum(row['correct'] for row in rows[-len(methods):]))), flush=True)
            (output/'partial.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
        summary = []
        for corpus in ('new_tools', 'previous'):
            for method in methods:
                for condition in ('clean', 'quiet', 'noise_15db'):
                    selected = [row for row in rows if (row['corpus'], row['method'], row['condition']) == (corpus, method, condition)]
                    summary.append(dict(corpus=corpus, method=method, condition=condition, count=len(selected),
                        correct=sum(row['correct'] for row in selected), mean_wer=round(statistics.mean(row['wer'] for row in selected), 4),
                        median_seconds=round(statistics.median(row['seconds'] for row in selected), 4)))
        backgrounds = []
        rng = np.random.default_rng(19)
        for name, audio in (('short_silence', np.zeros(8000, np.float32)), ('silence', np.zeros(48000, np.float32)),
                            ('short_noise', rng.normal(0, .003, 8000).astype(np.float32)),
                            ('noise', rng.normal(0, .003, 48000).astype(np.float32))):
            for method in methods:
                supplied = np.pad(audio, (4800, 4800)) if 'padding' in method else audio
                if not np.any(audio) or not recognizer._есть_речь(audio): heard = ''
                else:
                    result = raw.transcribe(speech_to_text.normalize_quiet_audio(supplied), language='ru', fp16=device == 'cuda',
                        initial_prompt=None if 'without_prompt' in method else prompt,
                        temperature=speech_to_text.TEMPERATURES, beam_size=speech_to_text.BEAM_SIZE,
                        best_of=5, condition_on_previous_text=False)
                    heard = (result.get('text') or '').strip()
                    if speech_to_text.looks_like_hallucination(heard): heard = ''
                backgrounds.append(dict(name=name, method=method, heard=heard))
        report = dict(summary=summary, rows=rows, backgrounds=backgrounds, checkpoint_sha256=original_sha, source_wavs=wavs,
                      model=args.model, engine=recognizer.engine, device=device,
                      gpu=torch.cuda.get_device_name(0) if device == 'cuda' else None,
                      torch=torch.__version__, load_seconds=round(load_seconds, 4),
                      microphone_used=False, playback_used=False, commands_executed=False)
        (output/'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(summary), flush=True)
    finally:
        if not model_home.resolve().is_relative_to(output): raise RuntimeError('Invalid cleanup path')
        shutil.rmtree(model_home)

if __name__ == '__main__': main()
