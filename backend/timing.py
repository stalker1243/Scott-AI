"""
Замеры времени по этапам обработки запроса.

Смысл: решать, что оптимизировать (и нужно ли вообще переписывать что-то на
C++/Rust), по реальным цифрам, а не по догадкам. Ответ Scott складывается из
нескольких очень разных по природе этапов — распознавание речи, локальные
правила, поход в LLM по сети, синтез речи, выполнение команды в ОС — и без
замеров невозможно сказать, какой из них съедает время на самом деле.

Использование:

    from timing import stage

    with stage("llm.groq"):
        answer = client.chat(...)

Сводка доступна через GET /timings, сырые замеры пишутся в logs/timings.jsonl
(можно выключить переменной окружения TIMING_LOG=0).
"""

import json
import os
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from pathlib import Path
from typing import Deque, Dict, Optional
try:
    from .support_logs import backend_log_directory, private_directory
except ImportError:
    from support_logs import backend_log_directory, private_directory

# Сколько последних замеров держим в памяти на каждый этап — хватает для
# устойчивых медианы и p95, но не растёт бесконечно при долгой работе.
_MAX_SAMPLES = 500

_lock = threading.Lock()
_log_lock = threading.Lock()
LOG_LIMIT = 2 * 1024 * 1024
_samples: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=_MAX_SAMPLES))
_counts: Dict[str, int] = defaultdict(int)
_errors: Dict[str, int] = defaultdict(int)
_started_at = time.time()

LOG_ENABLED = os.getenv("TIMING_LOG", "1") not in ("0", "false", "False", "no")
LOG_DIR = Path(os.getenv("TIMING_LOG_DIR") or os.getenv('SCOTT_LOG_DIR') or backend_log_directory())
_LOG_PATH = LOG_DIR / "timings.jsonl"


def record(stage_name: str, seconds: float, ok: bool = True, meta: Optional[dict] = None) -> None:
    """
    Записать один замер. Никогда не бросает исключение — сбой сбора статистики
    не должен ронять сам запрос, ради которого всё это работает.
    """
    try:
        with _lock:
            _samples[stage_name].append(seconds)
            _counts[stage_name] += 1
            if not ok:
                _errors[stage_name] += 1

        if LOG_ENABLED:
            private_directory(LOG_DIR)
            entry = {
                "ts": round(time.time(), 3),
                "stage": stage_name,
                "ms": round(seconds * 1000, 2),
                "ok": ok,
            }
            if meta:
                entry["meta"] = meta
            with _log_lock:
                if _LOG_PATH.is_symlink():
                    return
                if _LOG_PATH.exists() and _LOG_PATH.stat().st_size >= LOG_LIMIT:
                    for index in (2, 1):
                        source = _LOG_PATH if index == 1 else Path(str(_LOG_PATH)+'.1')
                        target = Path(str(_LOG_PATH)+f'.{index}')
                        if source.is_symlink() or target.is_symlink():
                            continue
                        if source.exists():
                            source.replace(target)
                with open(_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


@contextmanager
def stage(name: str, meta: Optional[dict] = None):
    """
    Замерить блок кода. Исключения пробрасываются дальше как есть — замер при
    этом помечается ok=False, чтобы в сводке было видно долю неудачных попыток.
    """
    start = time.perf_counter()
    ok = True
    try:
        yield
    except BaseException:
        ok = False
        raise
    finally:
        record(name, time.perf_counter() - start, ok=ok, meta=meta)


def _percentile(sorted_values, fraction: float) -> float:
    """Перцентиль по уже отсортированному списку (без numpy — он тут лишний)."""
    if not sorted_values:
        return 0.0
    index = int(round(fraction * (len(sorted_values) - 1)))
    return sorted_values[index]


def snapshot() -> dict:
    """
    Сводка по всем этапам: сколько раз вызывался, среднее/медиана/p95/максимум
    в миллисекундах. Отсортирована по суммарному вкладу — сверху то, что
    съедает больше всего времени в сумме, а не то, что просто медленное разово.
    """
    with _lock:
        data = {name: list(values) for name, values in _samples.items()}
        counts = dict(_counts)
        errors = dict(_errors)

    stages = []
    for name, values in data.items():
        if not values:
            continue
        ordered = sorted(values)
        total_ms = sum(values) * 1000
        stages.append({
            "stage": name,
            "calls": counts.get(name, len(values)),
            "errors": errors.get(name, 0),
            "avg_ms": round(sum(values) / len(values) * 1000, 1),
            "median_ms": round(_percentile(ordered, 0.5) * 1000, 1),
            "p95_ms": round(_percentile(ordered, 0.95) * 1000, 1),
            "max_ms": round(ordered[-1] * 1000, 1),
            # Суммарный вклад по последним замерам — именно он показывает,
            # где на самом деле "живёт" время при обычном использовании.
            "total_ms": round(total_ms, 1),
        })

    stages.sort(key=lambda s: s["total_ms"], reverse=True)
    return {
        "uptime_sec": round(time.time() - _started_at, 1),
        "samples_per_stage_limit": _MAX_SAMPLES,
        "log_file": str(_LOG_PATH) if LOG_ENABLED else None,
        "stages": stages,
    }


def reset() -> None:
    """Сбросить накопленную статистику (сырой лог на диске не трогаем)."""
    global _started_at
    with _lock:
        _samples.clear()
        _counts.clear()
        _errors.clear()
        _started_at = time.time()
