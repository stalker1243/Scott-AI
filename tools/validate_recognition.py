"""Before/after STT with an untouched baseline and synthetic activation controls."""
import argparse
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import statistics
import sys
import time

from compare_recognition import ROOT, read_wav, sha
from check_voice_path import save_wav

CONTROLS = (
    'Скотт, стоп', 'Скотт, хватит', 'Скотт, замолчи', 'Скотт, достаточно',
    'Скотт, скажи слово стоп', 'Скотт, не говори стоп',
    'Скотт, не выключай звук', 'Спасибо Скотт',
    'Код, стоп', 'Кот, стоп', 'Голос, голос, голос', 'Нет, нет, нет',
    'Скотт, сколько времени', 'Скотт, тише',
    'Скотт, посчитай два плюс два', 'Скотт, не открывай браузер',
)

def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'): stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--silero-checkpoint', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    parser.add_argument('--reuse-controls', type=Path)
    args = parser.parse_args()
    if args.reuse_controls:
        args.reuse_controls = args.reuse_controls.resolve()
        if not args.reuse_controls.is_relative_to(ROOT/'reports') or not args.reuse_controls.is_dir():
            parser.error('Reusable controls must be inside reports')
    output = args.output.resolve()
    if not output.is_relative_to(ROOT/'reports') or output.exists(): parser.error('Choose a new folder under reports')
    if not all(path.is_file() for path in (args.checkpoint, args.silero_checkpoint, args.baseline)):
        parser.error('Checkpoints and baseline must already exist')
    output.mkdir(parents=True)
    source = output/'source/backend'; source.mkdir(parents=True)
    for path in (ROOT/'backend').glob('*.py'): shutil.copy2(path, source/path.name)
    shutil.copy2(args.baseline, output/'baseline.py')
    (source.parent/'.env').write_text('WARMUP_MODELS=0\nSCOTT_SEMANTIC_MEMORY=0\n', encoding='utf-8')
    model_home = source/'data/models/whisper'; model_home.mkdir(parents=True)
    checkpoint = model_home/'large-v3-turbo.pt'; shutil.copy2(args.checkpoint, checkpoint)
    checkpoint_sha = sha(args.checkpoint); assert sha(checkpoint) == checkpoint_sha
    silero_copy = output/'model-input/v4_ru.pt'; silero_copy.parent.mkdir()
    shutil.copy2(args.silero_checkpoint, silero_copy)
    silero_sha = sha(args.silero_checkpoint); assert sha(silero_copy) == silero_sha
    sys.path.insert(0, str(source)); sys.dont_write_bytecode = True; os.chdir(source)
    os.environ.update(WHISPER_ENGINE='openai', WHISPER_SHORT_PADDING_MS='300', WARMUP_MODELS='0',
        SCOTT_SEMANTIC_MEMORY='0', OPENAI_API_KEY='', GROQ_API_KEY='', DEEPSEEK_API_KEY='', AI_PROVIDER='', AI_MODEL='')
    from testing_guard import install
    install([ROOT/'backend/data', ROOT/'data', ROOT/'.env', ROOT/'audio_cache'])
    try:
        import numpy as np
        import torch
        from scipy.signal import resample_poly
        import speech_to_text as stt
        import speech_text
        import understanding
        import accuracy_voice
        import browser_commands
        import check_recognition
        from command_parser import CommandParser
        from fast_intent import get_fast_intent_engine
        from question_answerer import get_question_answerer
        from voice_name_trigger import check_voice_trigger
        device = args.device if args.device == 'cpu' or torch.cuda.is_available() else 'cpu'
        current = stt.Recognizer('turbo', device); current.load()
        spec = importlib.util.spec_from_file_location('baseline_stt', output/'baseline.py')
        baseline_module = importlib.util.module_from_spec(spec); spec.loader.exec_module(baseline_module)
        before = baseline_module.Recognizer('turbo', current.device)
        before.engine = current.engine; before._model = current._model
        engines = dict(intent_engine=get_fast_intent_engine(), parser=CommandParser(), answerer=get_question_answerer())
        def decide(text):
            trigger = check_voice_trigger(text)
            if not trigger.has_trigger: return None
            command = trigger.command_text
            if command.casefold().strip(' .,!?:') in ('стоп', 'хватит', 'замолчи', 'достаточно'):
                return understanding.Decision(kind='interrupt')
            browser = browser_commands.parse(command)
            return understanding.Decision(kind='browser', parsed=browser) if browser else understanding.understand(command, **engines)
        def correct(expected, actual):
            return actual is None if expected is None else accuracy_voice._same_decision(expected, actual)
        samples = []
        trial = ROOT/'reports/voice-path/audio-trial-2'
        for row in json.loads((trial/'result.json').read_text(encoding='utf-8'))['rows']:
            samples.append(('new_tools', row['reference'], row['condition'], 'original', read_wav(trial/row['audio'])))
        for index, text in enumerate(check_recognition.PHRASES):
            voice = ('aidar', 'eugene')[index % 2]
            values = read_wav(ROOT/f'reports/recognition-turbo/{index:02}-{voice}.wav')
            for condition, audio in check_recognition.variants(values, index).items():
                samples.append(('previous', text, condition, voice, audio))
        model = torch.package.PackageImporter(io.BytesIO(silero_copy.read_bytes())).load_pickle('tts_models', 'model')
        model.to(torch.device(device))
        rng = np.random.default_rng(58)
        for voice in ('aidar', 'eugene', 'baya', 'kseniya'):
            for index, text in enumerate(CONTROLS):
                if args.reuse_controls:
                    for condition in ('clean', 'noise_15db'):
                        path = args.reuse_controls/f'control-{voice}-{index:02}-{condition}.wav'
                        samples.append(('activation_controls', text, condition, voice, read_wav(path)))
                    continue
                with torch.inference_mode():
                    values = model.apply_tts(text=speech_text.prepare_for_speech(text), speaker=voice,
                        sample_rate=48000, put_accent=True, put_yo=True).detach().cpu().numpy()
                values = resample_poly(values, 1, 3).astype(np.float32)
                noise = rng.normal(0, np.sqrt(np.mean(values.astype(np.float64)**2))/(10**(15/20)), len(values)).astype(np.float32)
                for condition, audio in (('clean', values), ('noise_15db', np.clip(values+noise, -.98, .98))):
                    path = output/f'control-{voice}-{index:02}-{condition}.wav'
                    save_wav(path, audio, 16000)
                    samples.append(('activation_controls', text, condition, voice, read_wav(path)))
        rows = []
        for index, (corpus, text, condition, voice, audio) in enumerate(samples):
            expected = decide(text)
            for name, recognizer in (('before', before), ('current', current)):
                torch.manual_seed(1243)
                started = time.perf_counter(); heard = recognizer.transcribe(audio); elapsed = time.perf_counter()-started
                actual = decide(heard)
                rows.append(dict(corpus=corpus, reference=text, condition=condition, voice=voice, method=name,
                    heard=heard, correct=correct(expected, actual), unexpected_activation=expected is None and actual is not None,
                    wer=round(check_recognition.word_error_rate(check_recognition.words(text), check_recognition.words(heard)), 4),
                    seconds=round(elapsed, 4), clip_seconds=round(len(audio)/16000, 4)))
            if index % 8 == 0: print(json.dumps(dict(index=index, total=len(samples))), flush=True)
            (output/'partial.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
        backgrounds = []
        for index in range(12):
            length = (8000, 16000, 48000)[index % 3]
            values = rng.normal(0, .003, length).astype(np.float32)
            for name, recognizer in (('before', before), ('current', current)):
                torch.manual_seed(1243)
                heard = recognizer.transcribe(values)
                backgrounds.append(dict(noise_seed=index, seconds=length/16000, method=name, heard=heard,
                                        has_activation=decide(heard) is not None))
        assert current.transcribe(np.zeros(8000, np.float32)) == ''
        summary = []
        for corpus in ('new_tools', 'previous', 'activation_controls'):
            for method in ('before', 'current'):
                for condition in ('clean', 'quiet', 'noise_15db'):
                    selected = [row for row in rows if (row['corpus'], row['method'], row['condition']) == (corpus, method, condition)]
                    if selected: summary.append(dict(corpus=corpus, method=method, condition=condition, count=len(selected),
                        correct=sum(row['correct'] for row in selected), mean_wer=round(statistics.mean(row['wer'] for row in selected), 4),
                        unexpected_activations=sum(row['unexpected_activation'] for row in selected),
                        median_seconds=round(statistics.median(row['seconds'] for row in selected), 4)))
        report = dict(summary=summary, rows=rows, backgrounds=backgrounds, model='turbo', engine=current.engine,
                      device=current.device, checkpoint_sha256=checkpoint_sha, silero_sha256=silero_sha,
                      microphone_used=False, playback_used=False, commands_executed=False)
        (output/'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(summary), flush=True)
    finally:
        for path in (model_home, silero_copy.parent):
            if not path.resolve().is_relative_to(output): raise RuntimeError('Invalid cleanup path')
            shutil.rmtree(path)

if __name__ == '__main__': main()
