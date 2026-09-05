"""
Напоминания и отложенные действия.

Планировщик в проекте уже был, но не работал: задачи складывались в список,
поток вызывал `schedule.run_pending()` — а сами задачи в библиотеку `schedule`
никто не регистрировал. Команда принималась, появлялась в списке и не
выполнялась никогда. Здесь это сделано заново и проще: без сторонней
библиотеки, зато с проверкой временем.

Две вещи, которых прежнему решению не хватало принципиально.

**Задачи переживают перезапуск.** Напоминание «через час» бесполезно, если
Scott забудет о нём, стоит закрыть окно, — а он теперь ещё и работает в фоне,
где перезапуск незаметен.

**Разбор человеческого времени.** Голосом говорят «через десять минут» и «в
половину четвёртого», а не «HH:MM». Что не удалось разобрать — честно
отклоняется, вместо того чтобы молча запланировать не на то время.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional

STORE_PATH = Path(__file__).resolve().parent / "data" / "reminders.json"

# Как часто проверяем, не пора ли что-то выполнить. Пятнадцать секунд —
# компромисс: напоминание «в 15:00» срабатывает достаточно точно, а процесс не
# просыпается впустую слишком часто.
TICK_SECONDS = 15


@dataclass
class Reminder:
    """Одно отложенное дело."""

    id: str
    text: str
    due: str                      # ISO-время срабатывания
    kind: str = "remind"          # remind | command
    created: str = ""
    done: bool = False

    @property
    def due_at(self) -> datetime:
        return datetime.fromisoformat(self.due)


# ==================== Разбор времени ====================
#
# Формулировки взяты из живой речи, а не из головы: «через десять минут»,
# «в 15:30», «завтра в 9». Всё, что не подошло ни под один образец, отклоняется
# — лучше переспросить, чем поставить напоминание на случайное время.

WORD_NUMBERS = {
    "одну": 1, "один": 1, "две": 2, "два": 2, "три": 3, "четыре": 4, "пять": 5,
    "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10,
    "пятнадцать": 15, "двадцать": 20, "тридцать": 30, "сорок": 40, "сорок пять": 45,
}

# Устойчивые выражения, где числа нет вовсе или оно слито со словом.
# Проверяются ПЕРВЫМИ: общий образец ниже разбирает «через полчаса» как число
# «пол» плюс единицу «часа» и отказывается, не найдя такого числа.
FIXED_DELAYS = [
    (re.compile(r"через\s+полтора\s+час\w*", re.IGNORECASE), timedelta(minutes=90)),
    (re.compile(r"через\s+полчаса", re.IGNORECASE), timedelta(minutes=30)),
    (re.compile(r"через\s+час\b", re.IGNORECASE), timedelta(hours=1)),
    (re.compile(r"через\s+минуту", re.IGNORECASE), timedelta(minutes=1)),
    (re.compile(r"через\s+сутки|через\s+день", re.IGNORECASE), timedelta(days=1)),
    (re.compile(r"через\s+неделю", re.IGNORECASE), timedelta(weeks=1)),
]

RELATIVE = re.compile(
    r"через\s+(?P<amount>\d+|[а-яё]+)\s+(?P<unit>секунд\w*|минут\w*|час\w*|дн\w*|день|недел\w*)",
    re.IGNORECASE,
)

ABSOLUTE = re.compile(
    r"(?:в|к|на)\s+(?P<hour>\d{1,2})[:.](?P<minute>\d{2})",
    re.IGNORECASE,
)

ABSOLUTE_HOUR = re.compile(
    r"(?:в|к|на)\s+(?P<hour>\d{1,2})\s*(?:часов|часа|час)\b",
    re.IGNORECASE,
)

TOMORROW = re.compile(r"\bзавтра\b", re.IGNORECASE)

# Уточнения времени суток: на момент срабатывания не влияют (человек говорит
# «в 9 утра», имея в виду ровно 9:00), но из текста напоминания их нужно убрать.
DAYPART = re.compile(r"\b(утра|утром|дня|днём|днем|вечера|вечером|ночи|ночью)\b", re.IGNORECASE)


def _amount_to_number(raw: str) -> Optional[int]:
    if raw.isdigit():
        return int(raw)
    return WORD_NUMBERS.get(raw.lower())


def parse_time(text: str, now: Optional[datetime] = None) -> Optional[datetime]:
    """
    Превратить сказанное в момент времени.

    Возвращает None, если разобрать не удалось: вызывающий код тогда честно
    переспросит, а не поставит напоминание наугад.
    """
    now = now or datetime.now()
    lowered = text.lower()

    # Устойчивые выражения — первыми, см. комментарий у FIXED_DELAYS.
    for pattern, delta in FIXED_DELAYS:
        if pattern.search(lowered):
            return now + delta

    match = RELATIVE.search(lowered)
    if match:
        amount = _amount_to_number(match.group("amount"))
        if amount is None:
            return None
        unit = match.group("unit")
        if unit.startswith("секунд"):
            return now + timedelta(seconds=amount)
        if unit.startswith("минут"):
            return now + timedelta(minutes=amount)
        if unit.startswith("час"):
            return now + timedelta(hours=amount)
        if unit.startswith("недел"):
            return now + timedelta(weeks=amount)
        return now + timedelta(days=amount)

    match = ABSOLUTE.search(lowered) or ABSOLUTE_HOUR.search(lowered)
    if match:
        hour = int(match.group("hour"))
        minute = int(match.groupdict().get("minute") or 0)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None

        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if TOMORROW.search(lowered):
            target += timedelta(days=1)
        elif target <= now:
            # Время сегодня уже прошло — значит речь про завтра. Иначе
            # напоминание «в 9:00», поставленное вечером, сработало бы мгновенно.
            target += timedelta(days=1)
        return target

    return None


def extract_subject(text: str) -> str:
    """
    Вынуть из фразы то, о чём напомнить.

    Убирается обращение к времени и служебные слова: из «напомни через десять
    минут выключить плиту» остаётся «выключить плиту» — именно это Scott
    произнесёт вслух, когда придёт срок.
    """
    cleaned = text
    for pattern in (*(p for p, _ in FIXED_DELAYS), RELATIVE, ABSOLUTE, ABSOLUTE_HOUR, TOMORROW, DAYPART):
        cleaned = pattern.sub(" ", cleaned)

    cleaned = re.sub(
        r"^\s*(скотт[,\s]+)?(напомни(?:ть)?|поставь напоминание|разбуди|подскажи)\s*(мне\s+)?",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    # «о том, что» и «чтобы» — связки, которые не несут смысла в самом
    # напоминании: произносить «что выключить плиту» звучит косноязычно.
    cleaned = re.sub(r"^\s*(о\s+том[,\s]+)?(что\s+нужно|чтобы|что)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.!?—-")
    return cleaned


# ==================== Хранилище и выполнение ====================

class ReminderService:
    """
    Держит список дел и будит их в срок.

    Напоминания лежат в файле: Scott работает в фоне и может быть перезапущен
    незаметно для человека, а «через час» должно пережить это без потерь.
    """

    def __init__(self, on_fire: Optional[Callable[[Reminder], None]] = None):
        self.on_fire = on_fire
        self._items: List[Reminder] = []
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._load()

    # ---- хранение ----

    def _load(self) -> None:
        try:
            if STORE_PATH.exists():
                data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
                self._items = [Reminder(**item) for item in data if isinstance(item, dict)]
        except Exception as e:
            print(f"⚠️ Не удалось прочитать напоминания: {e}")
            self._items = []

    def _save(self) -> None:
        try:
            STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
            payload = [asdict(item) for item in self._items]
            STORE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"⚠️ Не удалось сохранить напоминания: {e}")

    # ---- управление ----

    def add(self, text: str, due: datetime, kind: str = "remind") -> Reminder:
        item = Reminder(
            id=uuid.uuid4().hex[:8],
            text=text,
            due=due.isoformat(timespec="seconds"),
            kind=kind,
            created=datetime.now().isoformat(timespec="seconds"),
        )
        with self._lock:
            self._items.append(item)
            self._save()
        self.start()
        return item

    def cancel(self, reminder_id: str) -> bool:
        with self._lock:
            before = len(self._items)
            self._items = [i for i in self._items if i.id != reminder_id]
            changed = len(self._items) != before
            if changed:
                self._save()
        return changed

    def pending(self) -> List[Reminder]:
        with self._lock:
            return [i for i in self._items if not i.done]

    def all(self) -> List[Reminder]:
        with self._lock:
            return list(self._items)

    def clear_done(self) -> int:
        with self._lock:
            before = len(self._items)
            self._items = [i for i in self._items if not i.done]
            self._save()
            return before - len(self._items)

    # ---- часы ----

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="scott-reminders", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        while self._running:
            time.sleep(TICK_SECONDS)
            self._fire_due()

    def _fire_due(self) -> None:
        now = datetime.now()
        due: List[Reminder] = []

        with self._lock:
            for item in self._items:
                if item.done:
                    continue
                try:
                    if item.due_at <= now:
                        item.done = True
                        due.append(item)
                except ValueError:
                    # Испорченная запись — помечаем выполненной, чтобы она не
                    # мешала остальным при каждой проверке.
                    item.done = True
            if due:
                self._save()

        for item in due:
            print(f"⏰ Напоминание: {item.text}")
            if self.on_fire:
                try:
                    self.on_fire(item)
                except Exception as e:
                    print(f"⚠️ Не удалось выполнить напоминание: {e}")
