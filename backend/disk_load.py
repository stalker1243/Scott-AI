"""
Насколько занят диск прямо сейчас.

Замечание с живого просмотра: лаунчер показывал диск на восемьдесят процентов,
хотя в диспетчере он почти не работал. Ошибки в расчёте не было — считалось
совершенно другое. `disk_usage().percent` это доля занятого МЕСТА, а диспетчер
показывает долю ВРЕМЕНИ, когда диск был занят работой. Числа не имеют друг к
другу отношения: на забитом диске, к которому никто не обращается, первое
равно ста, а второе нулю. Рядом с процессором, памятью и видеокартой стоять
должна нагрузка, иначе одна из четырёх величин означает не то, что остальные
три, и читать их вместе нельзя.

ПОЧЕМУ ЭТО ОТДЕЛЬНЫЙ МОДУЛЬ. Первая попытка считала нагрузку по полям
`read_time` и `write_time`, которые psutil обещает у счётчиков ввода-вывода.
На Linux они заполнены, а на Windows — нет: проверка показала, что за время
записи ста мегабайт `write_bytes` вырос на все сто, а `write_time` остался
нулём. То есть на основной для проекта системе честный по виду расчёт молча
давал ноль при любой нагрузке.

Поэтому здесь два пути. На Windows берётся тот же счётчик
производительности, по которому рисует диспетчер задач: доля времени простоя
физических дисков, вычтенная из ста. На остальных системах — прирост времени
обслуживания запросов, где он действительно есть.

Счётчик открывается один раз и живёт до конца работы: открывать его на каждый
опрос значило бы платить миллисекунды за величину, которая меняется медленнее.
"""

from __future__ import annotations

import platform
import time
from typing import Optional

try:
    import psutil
except Exception:  # pragma: no cover — psutil есть везде, где работает Scott
    psutil = None


WINDOWS = platform.system() == "Windows"

# Формат «двойная точность» для значения счётчика.
PDH_FMT_DOUBLE = 0x00000200


class _WindowsCounter:
    """
    Счётчик простоя дисков через системный интерфейс PDH.

    Тот же источник, что у диспетчера задач: он показывает не «активное
    время» напрямую, а считает его как сто минус простой. Мы делаем так же —
    иначе числа не сойдутся с тем, что человек видит рядом в диспетчере.
    """

    def __init__(self):
        self._query = None
        self._counter = None
        self._pdh = None
        self._primed = False

    def open(self) -> bool:
        """Открыть счётчик. Возвращает False, если система его не дала."""
        try:
            import ctypes
            from ctypes import wintypes

            pdh = ctypes.WinDLL("pdh")
            query = wintypes.HANDLE()

            if pdh.PdhOpenQueryW(None, 0, ctypes.byref(query)) != 0:
                return False

            counter = wintypes.HANDLE()

            # Английское имя счётчика берётся намеренно: на локализованной
            # Windows обычное имя переведено, и запрос по нему не находит
            # ничего.
            path = r"\PhysicalDisk(_Total)\% Idle Time"
            if pdh.PdhAddEnglishCounterW(query, path, 0, ctypes.byref(counter)) != 0:
                return False

            # Первый сбор задаёт точку отсчёта: значение появится только со
            # второго, и до тех пор счётчик отвечает отказом.
            pdh.PdhCollectQueryData(query)

            self._pdh = pdh
            self._query = query
            self._counter = counter
            return True
        except Exception:
            return False

    def read(self) -> Optional[float]:
        """Активность в процентах или None, если значения пока нет."""
        if self._pdh is None:
            return None

        try:
            import ctypes
            from ctypes import wintypes

            if self._pdh.PdhCollectQueryData(self._query) != 0:
                return None

            class Formatted(ctypes.Structure):
                _fields_ = [
                    ("CStatus", wintypes.DWORD),
                    ("doubleValue", ctypes.c_double),
                ]

            value = Formatted()
            status = self._pdh.PdhGetFormattedCounterValue(
                self._counter, PDH_FMT_DOUBLE, None, ctypes.byref(value))

            if status != 0:
                # Между первым и вторым сбором значения ещё нет — это не
                # поломка, а устройство счётчика.
                return None

            idle = max(0.0, min(100.0, value.doubleValue))
            return 100.0 - idle
        except Exception:
            return None


class DiskLoad:
    """
    Нагрузка на диск, посчитанная тем способом, который работает на этой
    системе.

    Объект живёт всё время работы процесса: у обоих способов есть состояние —
    открытый счётчик на Windows и предыдущий замер на остальных системах.
    """

    def __init__(self):
        self._counter = None
        self._mark = None
        self._last = 0.0

        if WINDOWS:
            counter = _WindowsCounter()
            if counter.open():
                self._counter = counter

    @property
    def source(self) -> str:
        """Чем считаем — полезно в диагностике, когда число выглядит странно."""
        if self._counter is not None:
            return "счётчик производительности Windows"
        return "время обслуживания запросов"

    def read(self) -> float:
        """Доля времени, когда диск был занят работой, в процентах."""
        if self._counter is not None:
            value = self._counter.read()
            if value is not None:
                self._last = value
            return self._last

        return self._read_from_io_times()

    def _read_from_io_times(self) -> float:
        """
        Прирост времени обслуживания запросов между двумя замерами.

        Работает там, где psutil эти поля заполняет. На Windows они всегда
        нулевые, и этот путь туда не попадает.
        """
        if psutil is None:
            return 0.0

        try:
            counters = psutil.disk_io_counters()
            if counters is None:
                return 0.0

            busy = getattr(counters, "read_time", 0) + getattr(counters, "write_time", 0)
            now = time.monotonic()

            previous = self._mark
            self._mark = (now, busy)

            if previous is None:
                # Счётчики отдают время, накопленное с запуска системы, и
                # сравнивать его не с чем. Показать накопленное за сутки как
                # нагрузку прямо сейчас значило бы соврать в первую секунду.
                return 0.0

            elapsed = now - previous[0]
            if elapsed <= 0:
                return self._last

            # Время обслуживания в миллисекундах, промежуток в секундах.
            share = (busy - previous[1]) / (elapsed * 1000) * 100

            # Параллельные запросы к нескольким дискам дают в сумме больше ста
            # процентов; человеку такое число ничего не скажет, а рядом с
            # процентами процессора выглядит поломкой.
            self._last = max(0.0, min(100.0, share))
            return self._last
        except Exception:
            return 0.0
