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
import asyncio
import os
import re
import tempfile
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    from . import protocol_schedule
except ImportError:
    import protocol_schedule

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
MAX_REPEATS = 20


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
    enabled: bool = True

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
    repeat_count: int = 1
    stop_on_error: bool = True

    # Когда Scott запускает протокол сам.
    #
    # Пусто — не запускает: протокол ждёт, пока его позовут. С расписанием он
    # превращается из ускорителя набора в настоящую автоматизацию — «по будням
    # в девять» человек приходит к готовому рабочему столу, ничего не сказав.
    schedule: Any = None

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    runs: int = 0
    last_run: Optional[str] = None
    created: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["steps"] = [asdict(step) for step in self.steps]
        data["schedule"] = self.schedule.to_dict() if self.schedule else None

        # Расписание словами — интерфейсу и ответу голосом: «по будням в
        # 09:00» понятнее, чем часы и список номеров дней.
        data["schedule_text"] = self.schedule.human() if self.schedule else ""
        return data

    def due(self, now: Optional[datetime] = None) -> bool:
        """Пора ли запускать по расписанию."""
        if not self.enabled or not self.schedule:
            return False

        последний = None
        if self.last_run:
            try:
                последний = datetime.fromisoformat(self.last_run)
            except ValueError:
                последний = None

        return self.schedule.due(now or datetime.now(), последний)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Protocol":
        raw_steps = data.get("steps") or []
        steps: List[Step] = []

        for item in raw_steps:
            if isinstance(item, dict):
                steps.append(Step(text=item.get("text", ""), pause=item.get("pause", 0), enabled=bool(item.get("enabled", True))))
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
            "repeat_count": int(data.get("repeat_count", 1)),
            "stop_on_error": bool(data.get("stop_on_error", True)),
        }

        protocol = Protocol(**known)

        # Эти поля восстанавливаются, только если они есть: файл мог быть
        # написан руками, и требовать от человека счётчик запусков глупо.
        protocol.id = data.get("id") or protocol.id
        protocol.runs = int(data.get("runs") or 0)
        protocol.last_run = data.get("last_run")
        protocol.created = data.get("created") or protocol.created

        # Расписание принимается и разобранным, и словами: файл могли написать
        # руками, и требовать там часы с номерами дней недели значило бы
        # закрыть эту дверь.
        сырое = data.get("schedule")
        if isinstance(сырое, dict):
            protocol.schedule = protocol_schedule.Schedule(
                hour=сырое.get("hour", 9),
                minute=сырое.get("minute", 0),
                days=сырое.get("days") or [],
                enabled=bool(сырое.get("enabled", True)),
            )
        elif isinstance(сырое, str) and сырое.strip():
            protocol.schedule = protocol_schedule.parse(сырое)

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
    index: int = 0
    iteration: int = 1


@dataclass
class RunResult:
    """Чем кончился протокол целиком."""

    name: str
    steps: List[StepResult] = field(default_factory=list)
    stopped_at: Optional[int] = None
    error: str = ""
    total: int = 0

    @property
    def ok(self) -> bool:
        return not self.error and self.stopped_at is None and all(step.ok for step in self.steps)

    def summary(self) -> str:
        """Что сказать человеку."""
        if self.error:
            return f"Протокол «{self.name}» не выполнен: {self.error}"

        done = len(self.steps) if self.stopped_at is None else self.stopped_at

        if self.stopped_at is not None:
            failed = self.steps[self.stopped_at] if self.stopped_at < len(self.steps) else None
            на_чём = f" на шаге «{failed.text}»" if failed else ""
            return (f"Протокол «{self.name}» остановлен{на_чём}. "
                    f"Выполнено шагов: {done} из {self.total or len(self.steps)}.")

        failed = sum(not step.ok for step in self.steps)
        if failed:
            return f"Протокол «{self.name}» завершён с ошибками: {failed} из {len(self.steps)} шагов."

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

    def _write(self, items: List[Protocol]) -> None:
        """Replace the file only after the entire new catalog has been written."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        filename = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix=self.path.name + ".", suffix=".tmp", delete=False) as stream:
                filename = stream.name
                json.dump([item.to_dict() for item in items], stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(filename, self.path)
        finally:
            if filename and os.path.exists(filename):
                os.unlink(filename)

    def _commit(self, items: List[Protocol]) -> Optional[str]:
        try:
            self._write(items)
        except (OSError, ValueError) as error:
            return f"Не удалось сохранить протоколы: {error}"
        existing = {p.id: p for p in self._items}
        committed = []
        for candidate in items:
            retained = existing.get(candidate.id)
            if retained is not None:
                retained.__dict__.update(candidate.__dict__)
            committed.append(retained if retained is not None else candidate)
        self._items = committed
        return None

    def _find(self, name: str = "", protocol_id: str = "") -> Optional[Protocol]:
        return next((p for p in self._items if p.id == protocol_id), None) if protocol_id else next(
            (p for p in self._items if normalize(p.name) == normalize(name)), None)

    @staticmethod
    def _validate(data: Dict[str, Any]) -> Protocol:
        name = (data.get("name") or "").strip()
        if not normalize(name) or len(name) > 100:
            raise ValueError("Имя должно содержать от 1 до 100 символов")
        repeat = data.get("repeat_count", 1)
        if isinstance(repeat, bool) or not isinstance(repeat, int) or not 1 <= repeat <= MAX_REPEATS:
            raise ValueError(f"Число повторов — от 1 до {MAX_REPEATS}")
        schedule = data.get("schedule")
        if isinstance(schedule, str) and schedule.strip() and protocol_schedule.parse(schedule) is None:
            raise ValueError("Не понял расписание. Напишите, например: «по будням в 09:00»")
        candidate = Protocol.from_dict({**data, "name": name})
        if not candidate.steps or len(candidate.steps) > MAX_STEPS:
            raise ValueError(f"В протоколе должно быть от 1 до {MAX_STEPS} шагов")
        if not any(step.enabled for step in candidate.steps):
            raise ValueError("Включите хотя бы один шаг")
        if any(len(step.text) > 2000 for step in candidate.steps):
            raise ValueError("Фраза шага не должна превышать 2000 символов")
        if len(candidate.description) > 2000 or len(candidate.phrases) > 20 or any(len(p) > 200 for p in candidate.phrases):
            raise ValueError("Описание — до 2000 символов, голосовые фразы — до 20 по 200 символов")
        candidate.phrases = list(dict.fromkeys(p.strip() for p in candidate.phrases))
        return candidate

    # ---- управление ----

    def all(self) -> List[Protocol]:
        with self._lock:
            return list(self._items)

    def get(self, name: str) -> Optional[Protocol]:
        with self._lock:
            return self._find(name)

    def get_by_id(self, protocol_id: str) -> Optional[Protocol]:
        with self._lock:
            return self._find(protocol_id=protocol_id)

    def add(self, name: str, steps: List[Any], phrases: Optional[List[str]] = None,
            description: str = "", schedule: str = "", enabled: bool = True,
            repeat_count: int = 1, stop_on_error: bool = True) -> Dict[str, Any]:
        try:
            protocol = self._validate(dict(name=name, steps=steps, phrases=phrases or [], description=description,
                                          schedule=schedule, enabled=enabled, repeat_count=repeat_count, stop_on_error=stop_on_error))
        except (ValueError, TypeError) as error:
            return {"success": False, "error": str(error)}
        with self._lock:
            if self._find(protocol.name):
                return {"success": False, "error": f"Протокол «{protocol.name}» уже есть"}
            error = self._commit([*self._items, protocol])
            if error:
                return {"success": False, "error": error}

        return {"success": True, "protocol": protocol.to_dict()}

    def update(self, original_name: str, **changes) -> Dict[str, Any]:
        return self._update(name=original_name, changes=changes)

    def update_by_id(self, protocol_id: str, **changes) -> Dict[str, Any]:
        return self._update(protocol_id=protocol_id, changes=changes)

    def _update(self, name: str = "", protocol_id: str = "", changes: Optional[Dict] = None) -> Dict[str, Any]:
        with self._lock:
            protocol = self._find(name, protocol_id)
            if protocol is None:
                return {"success": False, "error": "Протокол не найден"}
            allowed = {key: value for key, value in (changes or {}).items() if key in
                       {"name", "steps", "phrases", "description", "enabled", "schedule", "repeat_count", "stop_on_error"}}
            try:
                candidate = self._validate({**protocol.to_dict(), **allowed})
            except (ValueError, TypeError) as error:
                return {"success": False, "error": str(error)}
            if any(p.id != protocol.id and normalize(p.name) == normalize(candidate.name) for p in self._items):
                return {"success": False, "error": f"Протокол «{candidate.name}» уже есть"}
            items = [candidate if p.id == protocol.id else p for p in self._items]
            error = self._commit(items)
            if error:
                return {"success": False, "error": error}
            return {"success": True, "protocol": candidate.to_dict()}

    def delete(self, name: str) -> Dict[str, Any]:
        return self._delete(name=name)

    def delete_by_id(self, protocol_id: str) -> Dict[str, Any]:
        return self._delete(protocol_id=protocol_id)

    def _delete(self, name: str = "", protocol_id: str = "") -> Dict[str, Any]:
        with self._lock:
            protocol = self._find(name, protocol_id)
            if protocol is None:
                return {"success": False, "error": "Протокол не найден"}
            error = self._commit([p for p in self._items if p.id != protocol.id])
            return {"success": False, "error": error} if error else {"success": True, "message": f"Протокол «{protocol.name}» удалён"}

    def mark_run(self, protocol: Protocol) -> None:
        self._mark(protocol.id, successful=True)

    def mark_attempt(self, protocol: Protocol) -> None:
        """
        Отметить время попытки, не засчитывая её в число запусков.

        Нужно расписанию. Протокол, упавший на первом шаге, без отметки
        пробовался бы заново на каждом тике службы — весь льготный получас
        подряд. А в счётчике запусков ему делать нечего: он не выполнился, и
        цифра рядом с именем должна об этом молчать.
        """
        self._mark(protocol.id, successful=False)

    def _mark(self, protocol_id: str, successful: bool) -> None:
        with self._lock:
            protocol = self._find(protocol_id=protocol_id)
            if protocol is None:
                return
            candidate = Protocol.from_dict(protocol.to_dict())
            candidate.runs += int(successful)
            candidate.last_run = datetime.now().isoformat(timespec="seconds")
            error = self._commit([candidate if p.id == protocol_id else p for p in self._items])
            if error:
                raise OSError(error)

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
    if not 1 <= protocol.repeat_count <= MAX_REPEATS or not any(step.enabled for step in protocol.steps):
        return RunResult(name=protocol.name, error="нет включённых шагов или неверное число повторов")
    if len(protocol.steps) > MAX_STEPS:
        return RunResult(name=protocol.name, error=f"слишком много шагов, предел — {MAX_STEPS}")

    return None


async def run_async(protocol: Protocol,
                    execute: Callable[[str], Any],
                    sleep: Optional[Callable[[float], Any]] = None,
                    stop_on_error: Optional[bool] = None,
                    depth: int = 0,
                    progress: Optional[Callable[[Dict[str, Any]], None]] = None) -> RunResult:
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

    result = RunResult(name=protocol.name, total=sum(s.enabled for s in protocol.steps) * protocol.repeat_count)
    stop_on_error = protocol.stop_on_error if stop_on_error is None else stop_on_error
    for iteration, index, step in _execution_steps(protocol):
        # Command coroutines may finish without yielding. Let status/cancel
        # requests run between commands even when all pauses are zero.
        await asyncio.sleep(0)
        if progress:
            progress({"current": len(result.steps) + 1, "total": result.total, "text": step.text, "iteration": iteration})
        try:
            answer = await execute(step.text)
            ok, response = _read_answer(answer)
        except Exception as e:
            ok, response = False, str(e)

        result.steps.append(StepResult(text=step.text, ok=ok, response=response, index=index, iteration=iteration))
        if progress:
            progress({"current": len(result.steps), "total": result.total, "text": step.text, "iteration": iteration,
                      "step": asdict(result.steps[-1])})

        if not ok and stop_on_error:
            result.stopped_at = len(result.steps) - 1
            return result

        if step.pause and sleep:
            await sleep(step.pause)

    return result


def run(protocol: Protocol,
        execute: Callable[[str], Any],
        sleep: Optional[Callable[[float], Any]] = None,
        stop_on_error: Optional[bool] = None,
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

    result = RunResult(name=protocol.name, total=sum(s.enabled for s in protocol.steps) * protocol.repeat_count)
    stop_on_error = protocol.stop_on_error if stop_on_error is None else stop_on_error
    for iteration, index, step in _execution_steps(protocol):
        try:
            answer = execute(step.text)
            ok, response = _read_answer(answer)
        except Exception as e:
            ok, response = False, str(e)

        result.steps.append(StepResult(text=step.text, ok=ok, response=response, index=index, iteration=iteration))

        if not ok and stop_on_error:
            result.stopped_at = len(result.steps) - 1
            return result

        if step.pause and sleep:
            sleep(step.pause)

    return result


def _execution_steps(protocol: Protocol):
    for iteration in range(1, protocol.repeat_count + 1):
        for index, step in enumerate(protocol.steps):
            if step.enabled:
                yield iteration, index, step


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
