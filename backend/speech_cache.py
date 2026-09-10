"""
Заранее озвученные реплики: то, что Scott говорит чаще всего.

Синтез короткой фразы после прогрева моделей стоит в среднем 420 миллисекунд —
замер на этой машине. Немного, но эти фразы звучат после каждой команды:
«Готово, сэр», «Выполнено успешно», «Секунду». Из кэша та же фраза достаётся за
треть миллисекунды.

Кэш лежит на диске и переживает перезапуск, так что платится это один раз за
всю жизнь установки. Смена голоса меняет ключ, и набор озвучивается заново —
поэтому прогрев идёт в фоне и молча: он не должен ни задерживать запуск, ни
пугать человека сообщениями об ошибках, которые ему ничего не говорят.

Длинные ответы сюда не попадают намеренно. Их бесконечно много, а звучат они по
одному разу — заполнять ими диск бессмысленно.
"""

from __future__ import annotations

import time
from typing import List


def stock_phrases() -> List[str]:
    """
    Реплики, которые Scott произносит снова и снова.

    Собираются из тех же мест, откуда их берёт сам Scott, а не переписываются
    сюда списком: список копий разошёлся бы с оригиналом на первой же правке —
    как это уже случалось со словарями движков разбора.
    """
    phrases: List[str] = []

    # Ответы из профиля: подтверждения, отказы, приветствия, прощания.
    try:
        try:
            from .scott_profile import get_scott_profile
        except ImportError:
            from scott_profile import get_scott_profile

        responses = get_scott_profile().profile.get("responses", {})
        for kind in ("success", "error", "greeting", "farewell", "thinking"):
            phrases.extend(responses.get(kind, []))
    except Exception:
        pass

    # Заготовленные ответы на приветствия и разговор ни о чём.
    try:
        try:
            from .question_answerer import QuestionAnswerer
        except ImportError:
            from question_answerer import QuestionAnswerer

        phrases.extend(QuestionAnswerer.GREETING_RESPONSES.values())
        phrases.append("У меня всё отлично! А у тебя?")
    except Exception:
        pass

    # Короткие реплики «секунду», которыми Scott отзывается, пока думает.
    try:
        try:
            from . import main as scott_main
        except ImportError:
            import main as scott_main

        phrases.extend(getattr(scott_main, "THINKING_CUES", ()))
    except Exception:
        pass

    # Порядок сохраняем, повторы убираем: одна и та же фраза может прийти из
    # двух мест, а озвучивать её дважды незачем.
    seen = set()
    unique = []
    for phrase in phrases:
        text = (phrase or "").strip()
        if text and text not in seen:
            seen.add(text)
            unique.append(text)

    return unique


def warm(voice=None, phrases=None) -> dict:
    """
    Озвучить набор заранее, чтобы первое «Готово» прозвучало сразу.

    Возвращает сводку: сколько озвучено, сколько уже лежало в кэше и сколько
    это заняло. Ошибки не поднимаются наружу — прогрев дело необязательное, и
    ронять из-за него запуск нельзя.
    """
    if voice is None:
        try:
            from .scott_voice import get_scott_voice
        except ImportError:
            from scott_voice import get_scott_voice
        voice = get_scott_voice()

    if phrases is None:
        phrases = stock_phrases()

    started = time.perf_counter()
    prepared = 0
    failed = 0

    for phrase in phrases:
        try:
            if voice.speak_to_file(phrase):
                prepared += 1
            else:
                failed += 1
        except Exception:
            # Одна неудачная фраза не повод бросать остальные: скорее всего
            # дело в ней самой, а не в движке.
            failed += 1

    return {
        "prepared": prepared,
        "failed": failed,
        "total": len(phrases),
        "seconds": round(time.perf_counter() - started, 2),
    }
