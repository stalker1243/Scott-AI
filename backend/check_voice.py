"""Check local TTS -> STT -> command routing, without a microphone or execution.

    py -3.13 backend/check_voice.py

The selected voice is local Silero. Use cached models to run this offline.
"""

import argparse
import json
import math
import time
import sys
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

import device_settings
import silero_tts
import speech_to_text
import scott_voice
from scott_voice import ScottVoice
from voice_name_trigger import check_voice_trigger
from fast_intent import get_fast_intent_engine
from command_parser import get_command_parser
from question_answerer import get_question_answerer
from understanding import understand


def main():
    parser = argparse.ArgumentParser(description="Проверка голоса без микрофона и выполнения команд")
    parser.add_argument("--text", default="Скотт, найди информацию о солнечной системе.")
    parser.add_argument("--voice", choices=list(silero_tts.SILERO_VOICES), default="aidar")
    parser.add_argument("--model", default="small", help="Модель Whisper, например small или turbo")
    parser.add_argument("--suite", action="store_true", help="Корпус команд и проверка параметров")
    parser.add_argument("--all-voices", action="store_true", help="Короткая проверка остальных локальных голосов")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent.parent / "reports" / "voice-check")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.suite:
        return run_suite(args)

    # This check uses the installed local engines; no system speech worker or
    # network fallback is created, and nothing is sent to command execution.
    voice = ScottVoice.__new__(ScottVoice)
    voice.audio_dir = args.output
    voice.engine = None
    scott_voice.HAS_EDGE_TTS = False
    start = time.perf_counter()
    path = voice.speak_to_file(args.text, args.voice)
    synthesis_seconds = time.perf_counter() - start
    if not path or Path(path).suffix != ".wav":
        raise RuntimeError("Локальный синтез не создал WAV")
    rate, audio = wavfile.read(path)
    if audio.dtype.kind in "iu":
        limits = np.iinfo(audio.dtype)
        audio = audio.astype(np.float32) / max(abs(limits.min), limits.max)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    factor = math.gcd(rate, 16000)
    audio = resample_poly(audio, 16000 // factor, rate // factor).astype(np.float32)

    speech_to_text.ENGINE_CHOICE = "openai"
    recognizer = speech_to_text.Recognizer(args.model, device_settings.resolve_device("whisper"))
    recognizer.load()
    start = time.perf_counter()
    heard = recognizer.transcribe(audio)
    recognition_seconds = time.perf_counter() - start
    trigger = check_voice_trigger(heard)
    decision = understand(trigger.command_text, intent_engine=get_fast_intent_engine(),
                          parser=get_command_parser(), answerer=get_question_answerer())
    result = {
        "text": args.text, "heard": heard, "has_trigger": trigger.has_trigger,
        "command": trigger.command_text, "kind": decision.kind, "action": decision.action,
        "audio": str(path), "device": recognizer.device, "engine": recognizer.engine,
        "synthesis_seconds": round(synthesis_seconds, 3),
        "recognition_seconds": round(recognition_seconds, 3),
    }
    (args.output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if trigger.has_trigger and trigger.command_text and decision.kind == "action" else 1


def run_suite(args):
    import accuracy
    import accuracy_voice
    import understanding
    speech_to_text.ENGINE_CHOICE = 'openai'
    recognizer = speech_to_text.Recognizer(args.model, device_settings.resolve_device('whisper'))
    recognizer.load()
    engines = {'intent_engine': get_fast_intent_engine(), 'parser': get_command_parser(),
               'answerer': get_question_answerer()}
    controls = [{'фраза': text} for text in (
        'выбери голос Светланы', 'выбери голос Айдара', 'выключи озвучку',
        'включи озвучку', 'громкость голоса 50 процентов', 'говори тише',
        'измени характер голоса на четкий', 'какой голос выбран',
        'громкость голоса пятьдесят пять процентов', 'покажи голоса',
        'выбери голос Уильяма', 'выбери голос Флориана')]
    sample = controls + [{'фраза': text} for text in (
        'Скотт, найди в интернете рецепт борща', 'Скотт, открой блокнот',
        'Скотт, закрой браузер', 'Скотт, создай папку отчеты')]
    reports = {}
    for name in ([args.voice] + [v for v in silero_tts.SILERO_VOICES if v != args.voice]
                 if args.all_voices else [args.voice]):
        phrases = accuracy.load_phrases() + controls if name == args.voice else sample
        started = time.perf_counter()
        reports[name] = accuracy_voice.check(understanding, engines, recognizer, phrases,
            synthesize=lambda text, path: accuracy_voice._озвучить(text, path, name))
        reports[name]['seconds'] = round(time.perf_counter() - started, 2)
        print(f"{name}: {reports[name]['попаданий']}/{reports[name]['всего']}, {reports[name]['точность']}%", flush=True)
    backgrounds = {
        'silence': np.zeros(40000, dtype=np.float32),
        'quiet_noise': np.random.default_rng(42).normal(0, 0.00001, 40000).astype(np.float32),
    }
    background_results = {name: recognizer.transcribe(audio) for name, audio in backgrounds.items()}
    result = {'device': recognizer.device, 'engine': recognizer.engine,
              'speech_settings_phrases': len(controls),
              'text_routing': accuracy.check(understanding, engines), 'voices': reports,
              'background_transcripts': background_results}
    path = args.output / 'suite.json'
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Отчёт: {path}')
    for name, report in reports.items():
        if report['промахи']:
            print(name + '\n' + accuracy_voice.report(report))
    return 0 if (all(report['точность'] >= 90 for report in reports.values())
                 and not any(background_results.values())) else 1


if __name__ == "__main__":
    raise SystemExit(main())
