"""
Звук: куда говорить, откуда слушать, насколько громко и говорить ли вообще.

До сих пор всё это решала система. Scott говорил в устройство по умолчанию с
громкостью, заданной синтезатором, и замолчать не умел вовсе — а просьба
«помолчи» была нужна чаще, чем кажется: ночью, в наушниках у другого человека,
на созвоне. Единственным способом заткнуть его было выключить весь backend.

Здесь эти четыре решения собраны в одном месте и переживают перезапуск. Это
важнее, чем кажется: первый же пользователь пожаловался, что настройки
сбрасываются при закрытии программы, и заново выбирать наушники каждое утро —
ровно та мелочь, из-за которой перестают пользоваться.

Устройства хранятся не по номеру, а по имени. Номера в системе не постоянны:
достаточно воткнуть флешку со звуком или включить телевизор по HDMI, и то, что
вчера было третьим устройством, сегодня станет четвёртым — Scott заговорил бы
не туда. Имя же остаётся прежним, а по нему номер находится заново при каждом
запуске.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except Exception:  # pragma: no cover — машина без звуковой подсистемы
    sd = None
    HAS_SOUNDDEVICE = False

CONFIG_PATH = Path(__file__).resolve().parent / "data" / "audio_config.json"

DEFAULTS: Dict = {
    # Пустая строка — «как в системе». Отдельного значения «авто» не нужно:
    # отсутствие выбора и есть автоматика.
    "input_device": "",
    "output_device": "",

    # Проценты, а не доли: так понятнее и в файле, и в интерфейсе.
    "volume": 100,

    # Тихий режим: Scott продолжает слушать, понимать и выполнять — но молчит.
    "quiet": False,
}

# Выше сотни звук не станет громче — он начнёт хрипеть: значения выходят за
# отрезок, который принимает звуковая карта, и волна срезается по краям.
MAX_VOLUME = 100


def _load() -> Dict:
    settings = dict(DEFAULTS)
    try:
        if CONFIG_PATH.exists():
            stored = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                for key in DEFAULTS:
                    if key in stored:
                        settings[key] = stored[key]
    except Exception:
        # Испорченный файл не повод молчать или падать: берём значения по
        # умолчанию и работаем дальше.
        pass
    return _sanitize(settings)


def _sanitize(settings: Dict) -> Dict:
    """Привести значения к допустимым, что бы ни лежало в файле."""
    clean = dict(DEFAULTS)

    for key in ("input_device", "output_device"):
        value = settings.get(key, "")
        clean[key] = value.strip() if isinstance(value, str) else ""

    try:
        volume = int(round(float(settings.get("volume", 100))))
    except (TypeError, ValueError):
        volume = 100
    clean["volume"] = max(0, min(MAX_VOLUME, volume))

    clean["quiet"] = bool(settings.get("quiet", False))
    return clean


def _save(settings: Dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------- чтение

def get_settings() -> Dict:
    """Текущие настройки звука."""
    return _load()


def get_volume() -> float:
    """Громкость как множитель для звуковой волны: 0.0 — тишина, 1.0 — как есть."""
    return _load()["volume"] / 100.0


def is_quiet() -> bool:
    """Молчит ли Scott сейчас."""
    return _load()["quiet"]


def get_output_device() -> Optional[int]:
    """Номер устройства вывода — или None, если выбрано системное."""
    return _resolve_device(_load()["output_device"], want_input=False)


def get_input_device() -> Optional[int]:
    """Номер микрофона — или None, если выбран системный."""
    return _resolve_device(_load()["input_device"], want_input=True)


def _resolve_device(name: str, want_input: bool) -> Optional[int]:
    """
    Найти номер устройства по сохранённому имени.

    Возвращает None, если имя пустое или устройство исчезло — тогда звук пойдёт
    через системное. Наушники отключают, и это не повод остаться без голоса.
    """
    if not name or not HAS_SOUNDDEVICE:
        return None

    channels = "max_input_channels" if want_input else "max_output_channels"
    try:
        for index, info in enumerate(sd.query_devices()):
            if info.get(channels, 0) <= 0:
                continue
            if info.get("name", "") == name:
                return index
    except Exception as e:
        print(f"⚠️ Не удалось найти устройство «{name}»: {e}")

    print(f"⚠️ Устройство «{name}» не найдено — беру системное")
    return None


# ---------------------------------------------------------------- запись

def update(**changes) -> Dict:
    """
    Изменить настройки. Меняется только то, что передали.

    Возвращает полный набор настроек — вызывающему коду не приходится читать
    их отдельным запросом, чтобы показать результат.
    """
    settings = _load()
    for key, value in changes.items():
        if key in DEFAULTS and value is not None:
            settings[key] = value

    settings = _sanitize(settings)
    _save(settings)
    return settings


def set_quiet(quiet: bool) -> Dict:
    """Включить или выключить тихий режим."""
    return update(quiet=bool(quiet))


# ---------------------------------------------------------------- список

def list_devices() -> Dict[str, List[Dict]]:
    """
    Микрофоны и динамики, доступные в системе.

    Одно физическое устройство система часто показывает несколько раз — через
    разные звуковые подсистемы (MME, WASAPI, DirectSound на Windows). Человеку
    из этого списка выбирать тяжело, поэтому одинаковые имена схлопываются: имя
    и есть то, чем мы устройство запоминаем.
    """
    result: Dict[str, List[Dict]] = {"input": [], "output": []}
    if not HAS_SOUNDDEVICE:
        return result

    try:
        default_in, default_out = sd.default.device
        devices = list(enumerate(sd.query_devices()))
    except Exception as e:
        print(f"⚠️ Не удалось получить список звуковых устройств: {e}")
        return result

    for kind, channels, default_index in (
        ("input", "max_input_channels", default_in),
        ("output", "max_output_channels", default_out),
    ):
        found = []
        seen = set()
        for index, info in devices:
            if info.get(channels, 0) <= 0:
                continue

            name = info.get("name", "").strip()
            if not name or name in seen:
                continue
            seen.add(name)

            found.append({
                "index": index,
                "name": name,
                "channels": info.get(channels, 0),
                "default": index == default_index,
            })

        result[kind] = _drop_truncated(found)

    return result


def _drop_truncated(devices: List[Dict]) -> List[Dict]:
    """
    Убрать обрезанные повторы одного и того же устройства.

    Старая звуковая подсистема Windows (MME) обрезает имя до 31 знака, и рядом
    с «Динамики (High Definition Audio Device)» в списке стоит «Динамики (High
    Definition Audio». Для человека это один и тот же пункт дважды, причём
    выбрать он норовит первый — обрезанный.

    Отбрасываем то, что является началом другого имени. Полное имя
    предпочтительнее не только на вид: по нему устройство и запоминается, а
    обрезанное могло бы совпасть не с тем.
    """
    kept = []
    for device in devices:
        name = device["name"]

        longer = next(
            (other for other in devices
             if other is not device
             and other["name"] != name
             and other["name"].startswith(name)),
            None,
        )
        if longer is not None:
            # Пометку «по умолчанию» нельзя терять вместе с обрезанной строкой:
            # системным может значиться именно она.
            if device["default"]:
                longer["default"] = True
            continue

        kept.append(device)

    return kept


def describe() -> Dict:
    """Всё, что нужно интерфейсу, одним ответом."""
    settings = _load()
    return {
        "success": True,
        "available": HAS_SOUNDDEVICE,
        "settings": settings,
        "devices": list_devices(),
    }
