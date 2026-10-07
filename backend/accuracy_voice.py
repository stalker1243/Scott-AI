"""
Точность на слух: доходит ли сказанное до разбора неискажённым.

ЗАЧЕМ ОТДЕЛЬНО ОТ `accuracy`. Тот проверяет понимание текста: во что
превращается фраза, набранная в чате. Но голосом Scott умеет меньше — и
виноват не разбор, он у них общий, а то, что до разбора доходит. Живой пример
из журнала услышанного: человек сказал «открой Google Chrome», Whisper записал
«открой кукол хром», и искать по такому названию было нечего.

Проверка замыкает цепь: фраза произносится синтезом, слушается распознаванием
и разбирается — как в жизни, только без микрофона и комнаты.

ЧТО СЧИТАЕТСЯ ПОПАДАНИЕМ. Не дословное совпадение — оно и не нужно: «Скотт,
открой браузер.» с точкой на конце разберётся так же. Попадание — когда
услышанное приводит к ТОМУ ЖЕ решению, что и написанное. Именно это человек и
замечает: сказал голосом — получил не то, что получил бы в чате.

ЧЕГО ОНА НЕ ЗАМЕНЯЕТ. Микрофон, комнату и живой голос. Синтезированная речь
ровнее человеческой, поэтому здешние 100% не означают, что вслух всё
разберётся. Зато провал здесь означает провал и там — с запасом.

ПОЧЕМУ НЕ ГОНЯЕТСЯ СО ВСЕМИ ПРОВЕРКАМИ. Ей нужны обе модели и видеокарта, а
идёт она около минуты. Запускается отдельно: `python accuracy_voice.py`.
"""

from __future__ import annotations

import tempfile
import math
import re
import wave
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np


def _озвучить(текст: str, путь: str, voice=None) -> Optional[np.ndarray]:
    """
    Произнести фразу и вернуть звук так, как его слышит распознавание.

    Текст готовится тем же способом, что и настоящие ответы Scott: Silero
    выбрасывает латиницу молча, и без подготовки «открой Google Chrome»
    прозвучало бы как «открой».
    """
    try:
        from . import silero_tts
        from .speech_text import prepare_for_speech
    except ImportError:
        import silero_tts
        from speech_text import prepare_for_speech

    произносимое = prepare_for_speech(текст)
    if not произносимое:
        return None

    if not silero_tts.synthesize(произносимое, путь, voice):
        return None

    with wave.open(путь) as файл:
        частота = файл.getframerate()
        данные = np.frombuffer(файл.readframes(файл.getnframes()), dtype=np.int16)

    звук = данные.astype(np.float32) / 32768.0

    if частота != 16000:
        from scipy.signal import resample_poly
        factor = math.gcd(частота, 16000)
        звук = resample_poly(звук, 16000 // factor, частота // factor).astype(np.float32)

    return звук


def _normalize(value):
    if isinstance(value, str):
        return re.sub(r'\s+', ' ', value.casefold().replace('ё', 'е')).strip(' .,!?;:')
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    return value


def _same_decision(before, after):
    if after is None or (before.kind, before.action or '') != (after.kind, after.action or ''):
        return False
    if before.kind == 'refused':
        return before.message == after.message
    if before.parsed is not None and before.kind != 'question':
        if after.parsed is None:
            return False
        if (_parameter(before) != _parameter(after)
                or _normalize(before.parsed.context) != _normalize(after.parsed.context)):
            return False
    for field in ('service', 'query', 'memory', 'project', 'order'):
        if _normalize(getattr(before, field, None)) != _normalize(getattr(after, field, None)):
            return False
    before_when, after_when = getattr(before, 'when', None), getattr(after, 'when', None)
    if (before_when is None) != (after_when is None):
        return False
    if before_when is not None and abs((before_when - after_when).total_seconds()) > 1:
        return False
    return True


def _parameter(decision):
    value = _normalize(decision.parsed.main_param)
    if decision.action in {'open_app', 'close_app'}:
        from app_resolver import ALIASES
        # These aliases also reach the real app/process resolvers.
        value = ALIASES.get(value, value)
        if value == 'google chrome':
            value = 'chrome'
    elif decision.action == 'reminder':
        # Compare what the real reminder executor uses, including the due
        # time. Commas and digit spelling must not mask wrong times/subjects.
        from datetime import datetime
        from reminders import parse_time, extract_subject
        due = parse_time(value, datetime(2026, 1, 1, 12))
        return (_normalize(extract_subject(value)), due) if due else ('invalid_time', value)
    elif decision.action == 'system_command':
        from speech_text import expand_numbers
        value = _normalize(expand_numbers(value))
    elif decision.action == 'open_website':
        from command_executor import website_url
        try:
            value = website_url(value)
        except ValueError:
            pass
    return value


def check(understanding, engines: Dict, recognizer,
          phrases: Optional[List[Dict]] = None, synthesize=None) -> Dict:
    """
    Прогнать набор через синтез, слух и разбор.

    `recognizer` — настоящий распознаватель (`speech_to_text.Recognizer`),
    поднятый вызывающим: поднимать его здесь значило бы делать это на каждый
    прогон.
    """
    try:
        from . import accuracy
    except ImportError:
        import accuracy

    набор = phrases if phrases is not None else accuracy.load_phrases()

    попаданий = 0
    промахи: List[Dict] = []
    рассмотрено = 0

    with tempfile.TemporaryDirectory(prefix="scott_слух_") as папка:
        for номер, запись in enumerate(набор):
            фраза = запись.get("фраза", "")
            if not фраза:
                continue

            рассмотрено += 1
            путь = str(Path(папка) / f"ф{номер}.wav")

            звук = (synthesize or _озвучить)(фраза, путь)
            if звук is None:
                промахи.append({
                    "сказано": фраза,
                    "услышано": "(не удалось произнести)",
                    "вышло": "—",
                    "ожидалось": "—",
                })
                continue

            услышано = (recognizer.transcribe(звук, language="ru") or "").strip()

            было = understanding.understand(фраза, **engines)
            стало = understanding.understand(услышано, **engines) if услышано else None

            одинаково = _same_decision(было, стало)

            if одинаково:
                попаданий += 1
            else:
                промахи.append({
                    "сказано": фраза,
                    "услышано": услышано or "(тишина)",
                    "ожидалось": accuracy._описать(было.kind, было.action or "", getattr(было.parsed, 'main_param', '')),
                    "вышло": (accuracy._описать(стало.kind, стало.action or "", getattr(стало.parsed, 'main_param', ''))
                              if стало else "—"),
                })

    return {
        "всего": рассмотрено,
        "попаданий": попаданий,
        "промахов": len(промахи),
        "точность": round(попаданий / рассмотрено * 100, 1) if рассмотрено else 0.0,
        "промахи": промахи,
    }


def report(итог: Dict) -> str:
    """Отчёт словами: что услышано вместо сказанного и к чему это привело."""
    строки = [
        f"Точность на слух: {итог['точность']}% "
        f"({итог['попаданий']} из {итог['всего']})",
    ]

    if итог["промахи"]:
        строки.append("")
        строки.append("Услышано не то:")
        for промах in итог["промахи"]:
            строки.append(f"  сказано:  «{промах['сказано']}»")
            строки.append(f"  услышано: «{промах['услышано']}»")
            строки.append(f"      было бы: {промах['ожидалось']}   вышло: {промах['вышло']}")
            строки.append("")

    return "\n".join(строки)


def main() -> None:
    """Прогон руками: `python accuracy_voice.py`."""
    import contextlib
    import io as _io
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))

    import understanding
    from command_parser import CommandParser
    from fast_intent import get_fast_intent_engine
    from question_answerer import get_question_answerer
    from speech_to_text import Recognizer

    # Движки и модели шумят в вывод — глушим, чтобы отчёт читался.
    глушилка = _io.StringIO()
    with contextlib.redirect_stdout(глушилка):
        engines = {
            "intent_engine": get_fast_intent_engine(),
            "parser": CommandParser(),
            "answerer": get_question_answerer(),
        }

        распознаватель = Recognizer("small", "cuda")
        распознаватель.load()

        итог = check(understanding, engines, распознаватель)

    print(report(итог))


if __name__ == "__main__":
    main()
