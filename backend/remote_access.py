"""
Кто может командовать Scott издалека и что именно ему позволено.

Написано до всякого транспорта и намеренно ничего о нём не знает. Придёт
команда из Telegram, из мобильного приложения или из домашней сети — правила
одни и те же. Иначе каждый новый способ связи пришлось бы снабжать своей
охраной, и одна из них однажды оказалась бы слабее прочих.

ЧЕМ ЭТО ОТЛИЧАЕТСЯ ОТ ГОЛОСА. Человек у микрофона стоит у машины: он видит, что
происходит, и может остановить. Команда издалека приходит в пустую комнату. Поэтому:

* командовать может только привязанное устройство — привязка делается с самого
  компьютера, кодом, который живёт минуту;
* разрешено не всё, что Scott умеет вообще, а заметно меньше;
* каждая выполненная команда попадает в журнал — иначе о чужой команде вы не
  узнаете никогда.

ПОЧЕМУ БЕЛЫЙ СПИСОК, А НЕ ЧЁРНЫЙ. Перечислить опасное невозможно: Scott умеет
запускать программы, а значит умеет запустить что угодно. Перечислимо только
безопасное — и список этот короткий.
"""

from __future__ import annotations

import json
import secrets
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

STORE_PATH = Path(__file__).resolve().parent / "data" / "remote_access.json"
LOG_PATH = Path(__file__).resolve().parent / "data" / "remote_log.json"

# Сколько живёт код привязки.
#
# Минута — это ровно столько, сколько нужно, чтобы прочитать код с экрана и
# ввести его на телефоне. Код, живущий час, успевает попасть на фотографию
# экрана, в скриншот, в чужие глаза.
PAIRING_TTL = 60

# Сколько команд с одного устройства принимать в минуту.
#
# Не от злого умысла — от заклинившей кнопки и от повторов при плохой связи:
# двадцать одинаковых «выключи компьютер» подряд человек точно не имел в виду.
RATE_LIMIT_PER_MINUTE = 20

# Сколько записей журнала хранить.
MAX_LOG = 500


# ==================== Что можно издалека ====================
#
# Список намеренно короткий. Это не всё, что Scott умеет, — это то, что не
# причинит вреда, если команда придёт в пустую комнату или окажется чужой.

ALLOWED = {
    "open_app": "запустить программу",
    "open_folder": "открыть папку",
    "open_website": "открыть сайт",
    "search": "найти в интернете",
    "volume_up": "прибавить громкость",
    "volume_down": "убавить громкость",
    "brightness_up": "прибавить яркость",
    "brightness_down": "убавить яркость",
    "list_processes": "показать процессы",
    "system_info": "рассказать о состоянии машины",
    "reminder": "поставить напоминание",
    "question": "ответить на вопрос",
    "remember": "запомнить",
    "project": "открыть проект",
    "schedule": "отложить команду",
    "protocol": "выполнить протокол",
}

# Что издалека нельзя — с объяснением, которое увидит человек.
#
# Отказ без причины выглядит капризом, а здесь причина важная: эти действия
# необратимы или требуют присутствия.
DENIED = {
    "shutdown": "выключение компьютера издалека я не делаю — вдруг на нём идёт работа",
    "restart": "перезагрузку издалека я не делаю — вдруг на нём идёт работа",
    "sleep": "усыпление издалека я не делаю: разбудить его будет некому",
    "delete_file": "удаление файлов издалека не делаю — отменить это будет нельзя",
    "close_app": "закрытие программ издалека не делаю: в них может быть несохранённое",
    "kill_process": "завершение процессов издалека не делаю: в них может быть несохранённое",
    "powershell": "произвольные команды оболочки издалека не выполняю",
    "run_script": "запуск скриптов издалека не выполняю",
    "write_code": "писать и запускать код издалека не буду",
    "run_code": "писать и запускать код издалека не буду",
}


def is_allowed(kind: str) -> bool:
    """Позволено ли такое действие издалека."""
    return kind in ALLOWED


def refusal(kind: str) -> str:
    """Почему нельзя — словами для человека."""
    if kind in DENIED:
        return DENIED[kind]

    return ("Это я делаю только с самого компьютера: издалека вы не увидите, "
            "что происходит, и не сможете остановить")


# ==================== Хранилище ====================

def _load() -> Dict:
    try:
        if STORE_PATH.exists():
            данные = json.loads(STORE_PATH.read_text(encoding="utf-8"))
            if isinstance(данные, dict):
                данные.setdefault("devices", [])
                return данные
    except Exception:
        # Испорченный файл означает «никто не привязан»: Scott продолжит
        # работать, просто не будет принимать команды издалека. Это безопасный
        # исход — в отличие от обратного.
        pass
    return {"devices": []}


def _save(данные: Dict) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(данные, ensure_ascii=False, indent=2), encoding="utf-8")


def save_token(token: str) -> None:
    """
    Запомнить токен бота.

    Здесь, а не в .env: там лежат ключи, которые человек вставляет руками при
    установке, а этот приходит из интерфейса и меняется вместе с привязками.
    Файл лежит в data/ — папке, которая не уезжает в репозиторий.
    """
    данные = _load()
    данные["telegram_token"] = (token or "").strip()
    _save(данные)


def get_token() -> str:
    """Токен бота: из настроек или из окружения, если его вписали руками."""
    import os

    return (_load().get("telegram_token") or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()


# ==================== Привязка ====================

# Код живёт в памяти, а не в файле: он действует минуту, и переживать
# перезапуск ему незачем.
_pairing: Optional[Dict] = None


def start_pairing() -> Dict:
    """
    Завести код привязки. Показывается на экране компьютера.

    Шесть цифр: их читают с экрана и набирают на телефоне. Длиннее — не
    наберут, короче — угадают. При каждом вызове код новый: прежний перестаёт
    действовать, даже если минута не вышла.
    """
    global _pairing

    код = f"{secrets.randbelow(1000000):06d}"
    _pairing = {"code": код, "until": time.time() + PAIRING_TTL}

    return {"code": код, "expires_in": PAIRING_TTL}


def pairing_active() -> bool:
    return _pairing is not None and time.time() < _pairing["until"]


def cancel_pairing() -> None:
    global _pairing
    _pairing = None


def pair(code: str, name: str, channel: str, address: str = "") -> Dict:
    """
    Привязать устройство по коду.

    `channel` — каким путём оно будет командовать («telegram», «app»),
    `address` — куда отвечать: для Telegram это номер чата.

    Успешная привязка гасит код: одним кодом привязывается одно устройство.
    Иначе подсмотревший код успел бы привязать и своё.
    """
    global _pairing

    if not pairing_active():
        return {"success": False, "error": "Код не запрошен или уже истёк"}

    if (code or "").strip() != _pairing["code"]:
        return {"success": False, "error": "Неверный код"}

    данные = _load()

    устройство = {
        "id": uuid.uuid4().hex[:12],
        "name": (name or "Устройство").strip()[:60],
        "channel": channel,
        "address": str(address),
        "token": secrets.token_urlsafe(24),
        "paired": time.time(),
        "last_seen": 0.0,
    }

    данные["devices"].append(устройство)
    _save(данные)

    _pairing = None

    return {"success": True, "device": устройство}


def devices() -> List[Dict]:
    """Привязанные устройства — без ключей: показывать их незачем."""
    return [
        {к: з for к, з in у.items() if к != "token"}
        for у in _load().get("devices", [])
    ]


def forget(device_id: str) -> Dict:
    """
    Отвязать устройство.

    Единственная защита при потерянном телефоне, поэтому действует немедленно:
    ключ перестаёт работать в тот же миг.
    """
    данные = _load()
    осталось = [у for у in данные["devices"] if у.get("id") != device_id]

    if len(осталось) == len(данные["devices"]):
        return {"success": False, "error": "Такого устройства нет"}

    данные["devices"] = осталось
    _save(данные)
    return {"success": True}


def find_by_address(channel: str, address: str) -> Optional[Dict]:
    """Найти привязанное устройство по обратному адресу — например, по чату Telegram."""
    for устройство in _load().get("devices", []):
        if устройство.get("channel") == channel and устройство.get("address") == str(address):
            return устройство
    return None


def touch(device_id: str) -> None:
    """Запомнить, когда устройство давало о себе знать."""
    данные = _load()

    for устройство in данные["devices"]:
        if устройство.get("id") == device_id:
            устройство["last_seen"] = time.time()
            _save(данные)
            return


# ==================== Частота ====================

_recent: Dict[str, List[float]] = {}


def within_rate_limit(device_id: str) -> bool:
    """
    Не слишком ли часто. Считается по последней минуте.

    Защита не от злого умысла, а от заклинившей кнопки и повторов при плохой
    связи: двадцать одинаковых «открой браузер» подряд человек не имел в виду.
    """
    сейчас = time.time()
    недавние = [м for м in _recent.get(device_id, []) if сейчас - м < 60]

    if len(недавние) >= RATE_LIMIT_PER_MINUTE:
        _recent[device_id] = недавние
        return False

    недавние.append(сейчас)
    _recent[device_id] = недавние
    return True


# ==================== Журнал ====================

def log(device_id: str, device_name: str, text: str, outcome: str) -> None:
    """
    Записать выполненное издалека.

    Без журнала о чужой команде вы не узнаете никогда: она выполнится в пустой
    комнате и не оставит следа.
    """
    записи = read_log()

    записи.append({
        "at": time.time(),
        "device_id": device_id,
        "device": device_name,
        "text": text[:200],
        "outcome": outcome[:200],
    })

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(
        json.dumps(записи[-MAX_LOG:], ensure_ascii=False, indent=2), encoding="utf-8")


def read_log(limit: int = MAX_LOG) -> List[Dict]:
    try:
        if LOG_PATH.exists():
            записи = json.loads(LOG_PATH.read_text(encoding="utf-8"))
            if isinstance(записи, list):
                return записи[-limit:]
    except Exception:
        pass
    return []
