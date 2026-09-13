"""
Протоколы: именованная последовательность шагов.

«Протокол: рабочий день» — открыть редактор, открыть браузер, приглушить звук,
напомнить про созвон. Одна фраза вместо четырёх.

ПОЧЕМУ ЭТОГО НЕ ХВАТАЛО. В проекте уже три механизма автоматизации, и ни один
не умеет связать несколько действий подряд. Кастомная команда — одно действие
на одну фразу. IFTTT-правило — одно действие на одно срабатывание. Макрос
записывает движения мыши и нажатия клавиш, то есть повторяет руки человека, а
не его намерения: такой макрос ломается от переехавшего окна и ничего не знает
о том, что делает.

ШАГ — ЭТО ФРАЗА. Главное решение здесь: шаг протокола записан теми же словами,
какими человек сказал бы его голосом, — «открой браузер», а не
`{"action": "open_app", "param": "chrome"}`. Причин две. Первая: протоколу
достаётся весь разбор, который уже отлажен на сотнях фраз, и всё, что Scott
умеет по голосу, работает в протоколе с первого дня. Вторая: человек, который
составляет протокол, пишет то же, что и говорит, — ему не нужно знать ни одного
названия действия.

Плата за это — разбор фразы на каждом шаге. Он занимает меньше двадцати
миллисекунд, то есть на фоне самих действий его нет.

ЧТО ЗДЕСЬ НЕ ДЕЛАЕТСЯ. Модуль не исполняет шаги сам: он отдаёт их наружу через
переданную функцию. Разделение решения и последствий здесь ровно то же, что и
в `understanding.py`, и ради того же: протокол из шести шагов проверяется за
миллисекунды, не открывая ни одной программы.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

STORE_PATH = Path(__file__).resolve().parent / "data" / "protocols.json"

# Слова, которыми человек зовёт протокол: «запусти протокол уборка»,
# «выполни сценарий вечер». Само слово «протокол» тоже считается: «протокол
# рабочий день» — так короче, и именно так это звучит в фильмах, откуда
# название и взято.
PROTOCOL_WORDS = ("протокол", "сценарий", "режим")

LAUNCH_WORDS = ("запусти", "выполни", "включи", "активируй", "начни", "старт")

# Предел на длину протокола. Не защита от злого умысла, а защита от опечатки:
# протокол, который зовёт сам себя, иначе вешает Scott наглухо.
MAX_STEPS = 40
MAX_DEPTH = 3


@dataclass
class Step:
    """
    Один шаг: фраза и пауза после неё.

    Пауза нужна чаще, чем кажется. Программа, которую только что попросили
    открыться, не готова принять следующую команду сразу, и без паузы протокол
    успевает отдать все шаги раньше, чем откроется первое окно.
    """

    text: str
    pause: float = 0.0

    def __post_init__(self) -> None:
        self.text = (self.text or "").strip()
        self.pause = max(0.0, min(float(self.pause or 0), 60.0))


@dataclass
class Protocol:
    """Именованная последовательность шагов."""

    name: str
    steps: List[Step] = field(default_factory=list)

    # Чем протокол зовётся, кроме «протокол <имя>». Человек редко зовёт вещь
    # одним и тем же словом: «рабочий день», «за работу», «начали».
    phrases: List[str] = field(default_factory=list)

    description: str = ""
    enabled: bool = True

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    runs: int = 0
    last_run: Optional[str] = None
    created: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["steps"] = [asdict(step) for step in self.steps]
        return data

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Protocol":
        raw_steps = data.get("steps") or []
        steps: List[Step] = []

        for item in raw_steps:
            if isinstance(item, dict):
                steps.append(Step(text=item.get("text", ""), pause=item.get("pause", 0)))
            elif isinstance(item, str):
                # Протокол, записанный одним списком фраз без пауз. Такой вид
                # удобно писать руками, и отказываться его читать незачем.
                steps.append(Step(text=item))

        known = {
            "name": data.get("name", ""),
            "steps": [s for s in steps if s.text],
            "phrases": [p for p in (data.get("phrases") or []) if isinstance(p, str) and p.strip()],
            "description": data.get("description", "") or "",
            "enabled": bool(data.get("enabled", True)),
        }

        protocol = Protocol(**known)

        # Эти поля восстанавливаются, только если они есть: файл мог быть
        # написан руками, и требовать от человека счётчик запусков глупо.
        protocol.id = data.get("id") or protocol.id
        protocol.runs = int(data.get("runs") or 0)
        protocol.last_run = data.get("last_run")
        protocol.created = data.get("created") or protocol.created

        return protocol


def normalize(text: str) -> str:
    """
    Привести фразу к виду, в котором её можно сравнивать.

    Человек зовёт протокол то «Рабочий день», то «рабочий день!», то «рабочий
    день» с двумя пробелами. Точное сравнение строк на этом и ломается.
    """
    lowered = (text or "").lower().replace("ё", "е")
    cleaned = re.sub(r"[^\w\s]+", " ", lowered, flags=re.UNICODE)
    return re.sub(r"\s+", " ", cleaned).strip()


def _strip_launch(text: str) -> str:
    """
    Убрать обёртку «запусти протокол ...» и оставить имя.

    Слова снимаются по одному с начала, а не вырезаются откуда попало: иначе
    протокол с именем «включи свет» перестаёт зваться по имени.
    """
    words = normalize(text).split()

    while words and words[0] in LAUNCH_WORDS:
        words.pop(0)

    while words and words[0] in PROTOCOL_WORDS:
        words.pop(0)

    return " ".join(words)


@dataclass
class StepResult:
    """Чем кончился шаг."""

    text: str
    ok: bool
    response: str = ""


@dataclass
class RunResult:
    """Чем кончился протокол целиком."""

    name: str
    steps: List[StepResult] = field(default_factory=list)
    stopped_at: Optional[int] = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and self.stopped_at is None

    def summary(self) -> str:
        """Что сказать человеку."""
        if self.error:
            return f"Протокол «{self.name}» не выполнен: {self.error}"

        done = len(self.steps) if self.stopped_at is None else self.stopped_at

        if self.stopped_at is not None:
            failed = self.steps[self.stopped_at] if self.stopped_at < len(self.steps) else None
            на_чём = f" на шаге «{failed.text}»" if failed else ""
            return (f"Протокол «{self.name}» остановлен{на_чём}. "
                    f"Выполнено шагов: {done} из {len(self.steps)}.")

        return f"Протокол «{self.name}» выполнен. Шагов: {done}."


class ProtocolStore:
    """
    Хранит протоколы и находит их по фразе.

    Лежат в файле: Scott работает в фоне и может быть перезапущен незаметно для
    человека, а протоколы он составляет один раз и надолго.
    """

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else STORE_PATH
        self._items: List[Protocol] = []
        self._lock = threading.Lock()
        self._load()

    # ---- хранение ----

    def _load(self) -> None:
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._items = [Protocol.from_dict(item) for item in data if isinstance(item, dict)]
        except Exception as e:
            print(f"⚠️ Не удалось прочитать протоколы: {e}")
            self._items = []

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = [item.to_dict() for item in self._items]
            self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"⚠️ Не удалось сохранить протоколы: {e}")

    # ---- управление ----

    def all(self) -> List[Protocol]:
        with self._lock:
            return list(self._items)

    def get(self, name: str) -> Optional[Protocol]:
        target = normalize(name)
        with self._lock:
            for item in self._items:
                if normalize(item.name) == target:
                    return item
        return None

    def add(self, name: str, steps: List[Any], phrases: Optional[List[str]] = None,
            description: str = "") -> Dict[str, Any]:
        name = (name or "").strip()
        if not name:
            return {"success": False, "error": "У протокола должно быть имя"}

        if self.get(name):
            return {"success": False, "error": f"Протокол «{name}» уже есть"}

        protocol = Protocol.from_dict({
            "name": name,
            "steps": steps,
            "phrases": phrases or [],
            "description": description,
        })

        if not protocol.steps:
            return {"success": False, "error": "В протоколе нет ни одного шага"}

        if len(protocol.steps) > MAX_STEPS:
            return {"success": False, "error": f"Слишком много шагов, предел — {MAX_STEPS}"}

        with self._lock:
            self._items.append(protocol)
            self._save()

        return {"success": True, "protocol": protocol.to_dict()}

    def update(self, name: str, **changes) -> Dict[str, Any]:
        protocol = self.get(name)
        if not protocol:
            return {"success": False, "error": f"Протокол «{name}» не найден"}

        with self._lock:
            if "steps" in changes:
                fresh = Protocol.from_dict({"name": protocol.name, "steps": changes["steps"]})
                if not fresh.steps:
                    return {"success": False, "error": "В протоколе нет ни одного шага"}
                if len(fresh.steps) > MAX_STEPS:
                    return {"success": False, "error": f"Слишком много шагов, предел — {MAX_STEPS}"}
                protocol.steps = fresh.steps

            if "phrases" in changes:
                protocol.phrases = [p for p in changes["phrases"] if isinstance(p, str) and p.strip()]

            if "description" in changes:
                protocol.description = changes["description"] or ""

            if "enabled" in changes:
                protocol.enabled = bool(changes["enabled"])

            if changes.get("name"):
                protocol.name = changes["name"].strip()

            self._save()

        return {"success": True, "protocol": protocol.to_dict()}

    def delete(self, name: str) -> Dict[str, Any]:
        protocol = self.get(name)
        if not protocol:
            return {"success": False, "error": f"Протокол «{name}» не найден"}

        with self._lock:
            self._items = [p for p in self._items if p.id != protocol.id]
            self._save()

        return {"success": True, "message": f"Протокол «{protocol.name}» удалён"}

    def mark_run(self, protocol: Protocol) -> None:
        with self._lock:
            protocol.runs += 1
            protocol.last_run = datetime.now().isoformat(timespec="seconds")
            self._save()

    # ---- поиск по фразе ----

    def match(self, text: str) -> Optional[Protocol]:
        """
        Найти протокол, который человек позвал этой фразой.

        Сначала снимается обёртка «запусти протокол ...» — то, что осталось,
        сверяется с именем. Затем фраза целиком сверяется со списком
        собственных фраз протокола.

        Совпадение только точное. Искать протокол по вхождению слов — прямой
        путь к тому, что «открой браузер» запустит протокол «браузер» вместо
        браузера: протокол, названный обычным словом, начнёт перехватывать все
        фразы с этим словом.
        """
        whole = normalize(text)
        if not whole:
            return None

        bare = _strip_launch(text)
        # Обёртка снята — значит человек звал именно протокол. Без неё
        # засчитываем только точное совпадение с именем или своей фразой.
        called_explicitly = bare != whole

        with self._lock:
            items = [p for p in self._items if p.enabled]

        for protocol in items:
            if bare and normalize(protocol.name) == bare:
                return protocol

            if called_explicitly:
                continue

            for phrase in protocol.phrases:
                if normalize(phrase) == whole:
                    return protocol

        return None


def _refuse(protocol: Protocol, depth: int) -> Optional[RunResult]:
    """Причина не начинать вовсе, если она есть."""
    if depth >= MAX_DEPTH:
        return RunResult(name=protocol.name, error="протокол зовёт сам себя слишком глубоко")

    if not protocol.enabled:
        return RunResult(name=protocol.name, error="протокол отключён")

    return None


async def run_async(protocol: Protocol,
                    execute: Callable[[str], Any],
                    sleep: Optional[Callable[[float], Any]] = None,
                    stop_on_error: bool = True,
                    depth: int = 0) -> RunResult:
    """
    То же, что `run`, но для исполнителя-корутины.

    Два цикла вместо одного намеренно. Настоящее исполнение в проекте
    асинхронное — шаг уходит в `_process_command_impl`, — а проверять протоколы
    удобнее обычными синхронными функциями, и заставлять каждую проверку
    поднимать цикл событий ради трёх строк логики значило бы платить за это
    везде. Общее вынесено: решение «начинать ли» и разбор ответа шага.
    """
    refusal = _refuse(protocol, depth)
    if refusal is not None:
        return refusal

    result = RunResult(name=protocol.name)

    for index, step in enumerate(protocol.steps):
        try:
            answer = await execute(step.text)
            ok, response = _read_answer(answer)
        except Exception as e:
            ok, response = False, str(e)

        result.steps.append(StepResult(text=step.text, ok=ok, response=response))

        if not ok and stop_on_error:
            result.stopped_at = index
            return result

        if step.pause and sleep:
            await sleep(step.pause)

    return result


def run(protocol: Protocol,
        execute: Callable[[str], Any],
        sleep: Optional[Callable[[float], Any]] = None,
        stop_on_error: bool = True,
        depth: int = 0) -> RunResult:
    """
    Выполнить протокол, отдавая каждый шаг наружу.

    `execute` получает фразу шага и возвращает всё, что угодно: строку ответа,
    словарь, ничего. Ошибку он может либо вернуть, либо бросить — здесь
    обрабатываются оба случая, потому что исполнители в проекте делают и так,
    и так.

    `stop_on_error` по умолчанию включён. Протокол — это последовательность, и
    шаги в ней обычно опираются друг на друга: открыть файл в редакторе,
    который не открылся, бессмысленно. Продолжать после сбоя можно попросить
    явно.
    """
    refusal = _refuse(protocol, depth)
    if refusal is not None:
        return refusal

    result = RunResult(name=protocol.name)

    for index, step in enumerate(protocol.steps):
        try:
            answer = execute(step.text)
            ok, response = _read_answer(answer)
        except Exception as e:
            ok, response = False, str(e)

        result.steps.append(StepResult(text=step.text, ok=ok, response=response))

        if not ok and stop_on_error:
            result.stopped_at = index
            return result

        if step.pause and sleep:
            sleep(step.pause)

    return result


def _read_answer(answer: Any) -> tuple[bool, str]:
    """
    Понять, удался ли шаг.

    Исполнители в проекте отвечают по-разному: кто строкой, кто словарём с
    признаком успеха, кто ничем. Разбирать это в каждом месте заново значило бы
    переписывать одну и ту же догадку.
    """
    if answer is None:
        return True, ""

    if isinstance(answer, dict):
        if answer.get("type") == "error" or answer.get("success") is False:
            return False, str(answer.get("response") or answer.get("error") or "ошибка")
        return True, str(answer.get("response") or "")

    return True, str(answer)
