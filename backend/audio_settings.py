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


# Через какую подсистему Windows разговаривать со звуком, по убыванию
# предпочтения. Порядок не случаен:
#
# * DirectSound называет устройства полностью и сам пересчитывает частоту
#   дискретизации. Последнее важнее, чем кажется: синтез отдаёт 24 или 48 кГц,
#   а звуковая карта может стоять на 44.1 — WASAPI в общем режиме такое просто
#   не примет и вернёт ошибку вместо звука.
# * MME умеет то же самое, но обрезает имена до 31 знака: «Динамики (High
#   Definition Audio» — так и остаётся, без закрывающей скобки.
# * WASAPI строже к частоте, зато точнее всех; берём, если первых двух нет.
#
# На не-Windows список пуст, и берётся первая попавшаяся подсистема — там она,
# как правило, одна (ALSA или CoreAudio).
PREFERRED_HOST_APIS = (
    "windows directsound",
    "mme",
    "windows wasapi",
)


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
        devices = list(enumerate(sd.query_devices()))
        chosen = _pick_host_api(sd.query_hostapis())
        allowed = set(sd.query_hostapis()[chosen]["devices"]) if chosen is not None else None

        # Сначала ищем в той подсистеме, из которой человеку и показывали
        # список. Имена в разных подсистемах совпадают дословно, и без этого
        # звук ушёл бы через ту, которую мы для себя не выбирали, — со своими
        # правилами насчёт частоты дискретизации.
        for only_chosen in (True, False):
            for index, info in devices:
                if info.get(channels, 0) <= 0:
                    continue
                if only_chosen and allowed is not None and index not in allowed:
                    continue
                if (info.get("name") or "").strip() == name:
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
    Микрофоны и динамики — по одному разу каждый.

    Windows показывает одно и то же устройство через несколько звуковых
    подсистем: на живой машине двенадцать строк вывода там, где физически три
    устройства. Имена при этом совпадают целиком, так что отличить повторы по
    строке невозможно — приходится выбирать одну подсистему и показывать только
    её. Список получается ровно таким, какой человек видит в настройках Windows.
    """
    result: Dict[str, List[Dict]] = {"input": [], "output": []}
    if not HAS_SOUNDDEVICE:
        return result

    try:
        devices = list(enumerate(sd.query_devices()))
        apis = sd.query_hostapis()
        default_in, default_out = sd.default.device
    except Exception as e:
        print(f"⚠️ Не удалось получить список звуковых устройств: {e}")
        return result

    chosen = _pick_host_api(apis)
    if chosen is None:
        return result

    # Имена устройств по умолчанию берём до отбора: сама система называет
    # умолчанием устройство из своей подсистемы, а не из выбранной нами.
    default_names = {
        "input": _device_name(devices, default_in),
        "output": _device_name(devices, default_out),
    }

    for kind, channels in (("input", "max_input_channels"), ("output", "max_output_channels")):
        found = []
        for index in apis[chosen]["devices"]:
            info = dict(devices[index][1]) if index < len(devices) else {}
            if info.get(channels, 0) <= 0:
                continue

            name = (info.get("name") or "").strip()
            if not name:
                continue

            found.append({
                "index": index,
                "name": name,
                "channels": info.get(channels, 0),
                "default": _same_device(name, default_names[kind]),
            })

        result[kind] = _drop_service_entries(found, devices, apis, chosen)

    return result


def _pick_host_api(apis) -> Optional[int]:
    """Подсистема, через которую будем работать со звуком."""
    by_name = {(api["name"] or "").strip().lower(): i for i, api in enumerate(apis)}

    for wanted in PREFERRED_HOST_APIS:
        if wanted in by_name:
            return by_name[wanted]

    # Ни одной знакомой: берём первую, где вообще есть устройства. Так работает
    # Linux и macOS, где подсистема обычно одна.
    for index, api in enumerate(apis):
        if api["devices"]:
            return index
    return None


def _device_name(devices, index) -> str:
    """Имя устройства по номеру; пусто, если номера нет."""
    if index is None or index < 0 or index >= len(devices):
        return ""
    return (devices[index][1].get("name") or "").strip()


def _same_device(name: str, other: str) -> bool:
    """
    Одно ли это устройство.

    Сравниваем с запасом: MME обрезает имена до 31 знака, и «Динамики (High
    Definition Audio» — то же самое, что «Динамики (High Definition Audio
    Device)». Именно из MME обычно и приходит устройство по умолчанию.
    """
    if not name or not other:
        return False
    return name == other or name.startswith(other) or other.startswith(name)


def _drop_service_entries(found: List[Dict], devices, apis, chosen: int) -> List[Dict]:
    """
    Убрать служебные записи подсистемы.

    У MME и DirectSound первым в списке стоит не устройство, а перенаправитель:
    «Переназначение звуковых устройств», «Первичный звуковой драйвер». Означают
    они «то, что выбрано в системе» — то есть ровно то, что у нас и так стоит
    первым пунктом, только менее понятными словами.

    Узнаём их не по названию — оно переводится на язык системы и полагаться на
    него нельзя, — а по тому, что настоящее устройство видно из нескольких
    подсистем сразу, а перенаправитель существует только в своей.
    """
    elsewhere = [
        (info.get("name") or "").strip()
        for index, info in devices
        if index not in apis[chosen]["devices"]
    ]

    kept = [d for d in found if any(_same_device(d["name"], other) for other in elsewhere)]

    # Если так не осталось ничего — значит подсистема на этой машине
    # единственная, и сравнивать было не с чем. Лучше показать всё, чем пустой
    # список: человеку тогда вообще не из чего выбирать.
    return kept or found


def describe() -> Dict:
    """Всё, что нужно интерфейсу, одним ответом."""
    settings = _load()
    return {
        "success": True,
        "available": HAS_SOUNDDEVICE,
        "settings": settings,
        "devices": list_devices(),
    }
