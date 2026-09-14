"""
Что у Scott работает прямо сейчас.

Сведения о машине в diagnostics.py отвечают на вопрос «как всё устроено», а
здесь — на вопрос «что сломано». Это разные вопросы, и второй задают чаще:
Scott не отвечает голосом, не слышит, не открывает программы — а почему, по
списку версий не поймёшь.

КАЖДАЯ ПРОВЕРКА ОТВЕЧАЕТ ЗА СЕБЯ. Упавшая не должна уносить остальные: человек
с отключённым микрофоном имеет право узнать, что у него с ключом ИИ. Поэтому
каждая обёрнута, а её падение само становится ответом — «проверить не удалось».

ТРИ СОСТОЯНИЯ, а не два. «Плохо» и «хорошо» мало: нет видеокарты — это не
поломка, а обстоятельство, при котором Scott работает медленнее. Смешав его с
настоящими отказами, мы научили бы человека не обращать внимания на красное.
"""

from __future__ import annotations

import os
import platform
import socket
from typing import Callable, Dict, List

OK = "ok"          # работает
WARN = "warn"      # работает, но не лучшим образом
FAIL = "fail"      # не работает


def _проверка(имя: str, заголовок: str, что_делать: Callable[[], Dict]) -> Dict:
    """
    Выполнить одну проверку, чем бы она ни кончилась.

    Падение проверки — тоже ответ, и притом честный: «не удалось выяснить»
    полезнее, чем пустое место или сорванный список.
    """
    try:
        итог = что_делать()
    except Exception as e:
        итог = {"state": FAIL, "detail": f"проверить не удалось: {e}"}

    return {"id": имя, "title": заголовок, **итог}


# ==================== Отдельные проверки ====================

def _микрофон() -> Dict:
    try:
        import sounddevice  # noqa: F401
    except Exception:
        return {"state": FAIL,
                "detail": "не установлена библиотека sounddevice — записывать звук нечем"}

    try:
        from . import listener as listener_module
    except ImportError:
        import listener as listener_module

    устройства = listener_module.list_input_devices()
    if not устройства:
        return {"state": FAIL, "detail": "микрофонов в системе не найдено"}

    return {"state": OK, "detail": f"устройств: {len(устройства)}"}


def _динамики() -> Dict:
    try:
        import sounddevice as sd
    except Exception:
        return {"state": FAIL, "detail": "не установлена библиотека sounddevice"}

    выходы = [у for у in sd.query_devices() if у.get("max_output_channels", 0) > 0]
    if not выходы:
        return {"state": FAIL, "detail": "устройств вывода не найдено — Scott будет беззвучен"}

    return {"state": OK, "detail": f"устройств: {len(выходы)}"}


def _голос() -> Dict:
    """Синтез речи: тот ли он, на который рассчитывали, и на чём считает."""
    try:
        from . import device_settings
    except ImportError:
        import device_settings

    устройство = device_settings.resolve_device("silero")

    try:
        from . import silero_tts
    except ImportError:
        import silero_tts

    if not getattr(silero_tts, "SILERO_AVAILABLE", True):
        return {"state": WARN,
                "detail": "Silero недоступен — Scott говорит запасным облачным голосом"}

    return {"state": OK, "detail": f"Silero, считает {_словами(устройство)}"}


def _распознавание() -> Dict:
    try:
        from . import device_settings
    except ImportError:
        import device_settings

    устройство = device_settings.resolve_device("whisper")

    движок = os.getenv("WHISPER_ENGINE", "auto")
    try:
        import faster_whisper  # noqa: F401
        быстрый = True
    except Exception:
        быстрый = False

    имя = "faster-whisper" if быстрый and движок != "openai" else "openai-whisper"

    if устройство == "cpu":
        # Не поломка: так Scott слышит, просто медленнее — около шести секунд на
        # фразу против доли секунды.
        return {"state": WARN,
                "detail": f"{имя}, считает процессор — фраза распознаётся дольше"}

    return {"state": OK, "detail": f"{имя}, считает {_словами(устройство)}"}


def _видеокарта() -> Dict:
    try:
        from . import device_settings
    except ImportError:
        import device_settings

    if device_settings.cuda_available():
        return {"state": OK, "detail": "CUDA доступна"}

    if device_settings.mps_available():
        return {"state": OK, "detail": "графика Apple (Metal) доступна"}

    # Отсутствие видеокарты — обстоятельство, а не отказ.
    if platform.system() == "Darwin":
        return {"state": WARN, "detail": "Metal недоступен — всё считает процессор"}

    return {"state": WARN,
            "detail": "не найдена — всё считает процессор. Возможно, torch поставлен без CUDA"}


def _модель_ии() -> Dict:
    # Через get_intelligent_answerer, а не через runtime: единственный экземпляр
    # на процесс живёт именно там, и спрашивать надо у него — иначе проверка
    # ответит «не настроена» при исправно работающей модели.
    try:
        from .intelligent_answerer import get_intelligent_answerer
    except ImportError:
        from intelligent_answerer import get_intelligent_answerer

    отвечающий = get_intelligent_answerer()
    if отвечающий is None or not getattr(отвечающий, "enabled", False):
        # Не отказ: команды Scott выполняет и без модели.
        return {"state": WARN,
                "detail": "не настроена — команды работают, но на вопросы отвечать некому"}

    провайдер = getattr(отвечающий, "api_provider", "") or "неизвестный провайдер"
    модель = getattr(отвечающий, "model", "") or ""

    return {"state": OK, "detail": f"{провайдер} / {модель}" if модель else провайдер}


def _интернет() -> Dict:
    """
    Есть ли выход наружу.

    Проверяется соединением, а не запросом страницы: нам нужен факт связи, а не
    чей-то ответ, и ждать его дольше секунды незачем — человек смотрит на
    страницу диагностики и ждёт.
    """
    try:
        with socket.create_connection(("1.1.1.1", 443), timeout=1.5):
            pass
    except OSError:
        return {"state": WARN,
                "detail": "нет связи — ответы ИИ и облачный голос работать не будут"}

    return {"state": OK, "detail": "есть"}


def _память_разговоров() -> Dict:
    """Файл, в котором Scott помнит разговоры. Недоступный — он забывает всё между запусками."""
    путь = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "memory.jsonl")

    if not os.path.exists(путь):
        return {"state": OK, "detail": "пока пуста — заполнится при первых разговорах"}

    размер = os.path.getsize(путь) / 1024
    if not os.access(путь, os.W_OK):
        return {"state": FAIL, "detail": "файл памяти недоступен для записи"}

    return {"state": OK, "detail": f"{размер:.0f} КБ"}


def _словами(устройство: str) -> str:
    return {
        "cuda": "видеокарта",
        "mps": "графика Apple",
        "cpu": "процессор",
    }.get(устройство, устройство)


# ==================== Всё вместе ====================

ПРОВЕРКИ = [
    ("microphone", "Микрофон", _микрофон),
    ("speakers", "Динамики", _динамики),
    ("recognition", "Распознавание речи", _распознавание),
    ("voice", "Голос", _голос),
    ("gpu", "Видеокарта", _видеокарта),
    ("ai", "Модель ИИ", _модель_ии),
    ("internet", "Интернет", _интернет),
    ("memory", "Память разговоров", _память_разговоров),
]


def run_all() -> Dict:
    """
    Выполнить все проверки и подвести итог.

    Итог нужен, чтобы человеку не пришлось читать восемь строк ради ответа
    «всё ли в порядке»: сперва он видит вывод, а подробности — если они ему
    понадобятся.
    """
    результаты: List[Dict] = [_проверка(имя, заголовок, что)
                              for имя, заголовок, что in ПРОВЕРКИ]

    отказов = sum(1 for р in результаты if р["state"] == FAIL)
    замечаний = sum(1 for р in результаты if р["state"] == WARN)

    if отказов:
        итог = FAIL
        словами = f"Не работает: {отказов}"
    elif замечаний:
        итог = WARN
        словами = f"Работает с оговорками: {замечаний}"
    else:
        итог = OK
        словами = "Всё работает"

    return {
        "success": True,
        "state": итог,
        "summary": словами,
        "checks": результаты,
    }


def as_text() -> str:
    """
    Тот же список словами — чтобы человек мог его скопировать и переслать.

    Это главный способ рассказать о поломке: вместо «у меня не работает» —
    восемь строк, по которым видно, что именно.
    """
    отчёт = run_all()

    значки = {OK: "[ ок ]", WARN: "[ ! ]", FAIL: "[ нет ]"}

    строки = [
        "Scott AI — проверка состояния",
        f"Система: {platform.system()} {platform.release()}",
        f"Итог: {отчёт['summary']}",
        "",
    ]

    for проверка in отчёт["checks"]:
        значок = значки.get(проверка["state"], "[ ? ]")
        строки.append(f"{значок} {проверка['title']}: {проверка.get('detail', '')}")

    return "\n".join(строки)
