"""Synthetic speech -> real Whisper -> input comparison. No microphone or actions.

Use explicit existing checkpoints; temporary copies protect installed resources.
Output and isolated source/settings always stay below this project's reports.
"""
import argparse
import hashlib
import html
import io
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
CASES = (
    'Скотт посчитай двадцать пять плюс десять',
    'Скотт посчитай двенадцать умножить на три',
    'Скотт сколько будет пятнадцать процентов от ста',
    'Скотт переведи два километра в метры',
    'Скотт запусти секундомер',
    'Скотт поставь секундомер на паузу',
    'Скотт сколько на секундомере',
    'Скотт продолжи секундомер',
    'Скотт покажи системную громкость',
    'Скотт установи системную громкость на тридцать процентов',
    'Скотт выключи системный звук',
    'Скотт подбрось монету',
    'Скотт какой завтра день недели',
    'Скотт поставь на паузу ютуб',
    'Скотт продолжи видео на ютубе',
    'Скотт стоп',
)

def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''): result.update(chunk)
    return result.hexdigest()

def save_wav(path, samples, rate):
    import numpy as np
    values = np.asarray(samples, dtype=np.float32)
    assert values.ndim == 1 and values.size and np.isfinite(values).all()
    pcm = np.rint(np.clip(values, -1, 1)*32767).astype('<i2')
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(rate)
        output.writeframes(pcm.tobytes())

def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'): stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--whisper-checkpoint', type=Path, required=True)
    parser.add_argument('--silero-checkpoint', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    parser.add_argument('--model', default='turbo')
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT/'reports').resolve()) or output.exists():
        parser.error('Choose a new directory inside reports')
    for source in (args.whisper_checkpoint, args.silero_checkpoint):
        if not source.is_file(): parser.error('Checkpoint file does not exist')
    output.mkdir(parents=True)
    source = output/'source/backend'
    source.mkdir(parents=True)
    for path in (ROOT/'backend').glob('*.py'): shutil.copy2(path, source/path.name)
    (source.parent/'.env').write_text('WARMUP_MODELS=0\nSCOTT_SEMANTIC_MEMORY=0\n', encoding='utf-8')
    whisper_home = source/'data/models/whisper'
    whisper_home.mkdir(parents=True)
    whisper_copy = whisper_home/('large-v3-turbo.pt' if args.model == 'turbo' else args.model+'.pt')
    silero_copy = output/'model-input/v4_ru.pt'
    silero_copy.parent.mkdir()
    hashes = {'whisper': digest(args.whisper_checkpoint), 'silero': digest(args.silero_checkpoint)}
    shutil.copy2(args.whisper_checkpoint, whisper_copy)
    shutil.copy2(args.silero_checkpoint, silero_copy)
    assert digest(whisper_copy) == hashes['whisper'] and digest(silero_copy) == hashes['silero']
    os.chdir(source)
    sys.path.insert(0, str(source))
    sys.dont_write_bytecode = True
    os.environ.update(WARMUP_MODELS='0', SCOTT_SEMANTIC_MEMORY='0', WHISPER_ENGINE='openai',
                      OPENAI_API_KEY='', GROQ_API_KEY='', DEEPSEEK_API_KEY='', AI_PROVIDER='', AI_MODEL='')
    from testing_guard import install
    install([ROOT/'backend/data', ROOT/'data', ROOT/'.env', ROOT/'audio_cache'])
    try:
        import numpy as np
        import torch
        from scipy.signal import resample_poly
        from speech_to_text import Recognizer
        import understanding
        import accuracy_voice
        import browser_commands
        from command_parser import CommandParser
        from fast_intent import get_fast_intent_engine
        from question_answerer import get_question_answerer
        from voice_name_trigger import check_voice_trigger
        from speech_text import prepare_for_speech
        device = args.device if args.device != 'cuda' or torch.cuda.is_available() else 'cpu'
        print(json.dumps({'phase': 'load', 'model': args.model, 'device': device}), flush=True)
        model = torch.package.PackageImporter(io.BytesIO(silero_copy.read_bytes())).load_pickle('tts_models', 'model')
        model.to(torch.device(device))
        recognizer = Recognizer(args.model, device)
        begin = time.perf_counter()
        recognizer.load()
        load_seconds = time.perf_counter()-begin
        engines = dict(intent_engine=get_fast_intent_engine(), parser=CommandParser(), answerer=get_question_answerer())
        def decide(text):
            trigger = check_voice_trigger(text)
            if not trigger.has_trigger: return None
            command = trigger.command_text
            if command.casefold().strip(' .,!?:') == 'стоп': return understanding.Decision(kind='interrupt')
            browser = browser_commands.parse(command)
            if browser: return understanding.Decision(kind='browser', parsed=browser)
            return understanding.understand(command, **engines)
        rows = []
        rng = np.random.default_rng(1243)
        for index, text in enumerate(CASES):
            voice = 'aidar' if index % 2 == 0 else 'eugene'
            started = time.perf_counter()
            with torch.inference_mode():
                audio = model.apply_tts(text=prepare_for_speech(text), speaker=voice,
                    sample_rate=48000, put_accent=True, put_yo=True).detach().cpu().numpy()
            synthesis_seconds = time.perf_counter()-started
            values = resample_poly(audio, 1, 3).astype(np.float32)
            variants = [('clean', values), ('quiet', values*.08)]
            noise = rng.normal(size=len(values)).astype(np.float32)
            rms = float(np.sqrt(np.mean(values.astype(np.float64)**2)))
            noise *= rms/(10**(15/20)*float(np.sqrt(np.mean(noise.astype(np.float64)**2))))
            variants.append(('noise_15db', np.clip(values+noise, -.98, .98)))
            expected = decide(text)
            assert expected is not None
            for condition, samples in variants:
                path = output/f'{index:02}-{voice}-{condition}.wav'
                save_wav(path, samples, 16000)
                started = time.perf_counter()
                heard = recognizer.transcribe(samples, language='ru')
                seconds = time.perf_counter()-started
                actual = decide(heard)
                correct = accuracy_voice._same_decision(expected, actual)
                rows.append(dict(reference=text, heard=heard, voice=voice, condition=condition,
                    audio=path.name, correct=correct, expected_kind=expected.kind,
                    actual_kind=actual.kind if actual else None, seconds=round(seconds, 4),
                    synthesis_seconds=round(synthesis_seconds, 4)))
            print(json.dumps({'case': index, 'correct': sum(row['correct'] for row in rows[-3:]),
                              'conditions': 3}), flush=True)
        backgrounds = {}
        for name, samples in (('silence', np.zeros(48000, np.float32)),
                              ('noise', rng.normal(0, .003, 48000).astype(np.float32))):
            backgrounds[name] = recognizer.transcribe(samples, language='ru')
        summary = {}
        for condition in ('clean', 'quiet', 'noise_15db'):
            selected = [row for row in rows if row['condition'] == condition]
            summary[condition] = dict(count=len(selected), correct=sum(row['correct'] for row in selected),
                median_seconds=round(statistics.median(row['seconds'] for row in selected), 4))
        report = dict(model=args.model, engine=recognizer.engine, device=recognizer.device,
            load_seconds=round(load_seconds, 4), checkpoint_sha256=hashes, summary=summary,
            backgrounds=backgrounds, rows=rows, microphone_used=False, playback_used=False,
            commands_executed=False, sources_snapshot=True)
        (output/'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        cards = ''.join(f'<tr><td>{html.escape(row["reference"])}</td><td>{row["condition"]}</td>'
            f'<td>{html.escape(row["heard"])}</td><td>{"✓" if row["correct"] else "Ошибка"}</td>'
            f'<td><audio controls preload="none" src="{row["audio"]}"></audio></td></tr>' for row in rows)
        page = '<!doctype html><html lang="ru"><meta charset="utf-8"><title>Проверка голосового пути</title>'
        page += '<style>body{font:16px system-ui;background:#131b29;color:#e7eef8;margin:32px}table{border-collapse:collapse;width:100%}td,th{padding:12px;border-bottom:1px solid #334155;text-align:left}audio{width:240px}pre{white-space:pre-wrap}</style>'
        page += '<h1>Голосовые команды: синтетическая проверка</h1><p>Микрофон и воспроизведение не включались. Команды не выполнялись.</p>'
        page += '<pre>'+html.escape(json.dumps(summary, ensure_ascii=False, indent=2))+'</pre><table><tr><th>Фраза</th><th>Условия</th><th>Распознано</th><th>Маршрут и параметры</th><th>Запись</th></tr>'+cards+'</table></html>'
        (output/'index.html').write_text(page, encoding='utf-8')
        print(json.dumps({'summary': summary, 'backgrounds': backgrounds}), flush=True)
    finally:
        # Delete only the exact, verified model-copy directories created above.
        for temporary in (whisper_home, silero_copy.parent):
            if not temporary.resolve().is_relative_to(output): raise RuntimeError('Unexpected cleanup path')
            shutil.rmtree(temporary)

if __name__ == '__main__': main()
