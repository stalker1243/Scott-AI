"""
Что звучит в колонках прямо сейчас — для эхоподавления.

Подавлению нужен опорный сигнал: тот же звук, что ушёл на воспроизведение,
выровненный по времени с тем, что услышал микрофон. Взять его неоткуда, кроме
как у проигрывателя, — и это как раз наше преимущество перед обычным
эхоподавлением, которому приходится перехватывать звук с устройства вывода.

ДВЕ ТРУДНОСТИ, обе про время.

Первая: частоты разные. Синтезатор отдаёт сорок восемь тысяч отсчётов в
секунду, микрофон пишет шестнадцать. Сигнал приводится к частоте микрофона
сразу при начале воспроизведения, а не на каждом блоке: за время ответа блоков
набегает сотня, и пересчитывать один и тот же звук сто раз незачем.

Вторая: запись отстаёт. Между «отдали звук» и «микрофон услышал» проходит от
сотни до нескольких сотен миллисекунд — буферы драйвера, колонки, воздух.
Величина своя на каждой машине и меряется корреляцией по первым полсекунды
ответа. Замеренное запоминается: заново считать его на каждом ответе не нужно,
пока не сменилось устройство вывода.

ПРИ ЛЮБОЙ БЕДЕ — ТИШИНА. Если опорного сигнала нет, он не той длины или
случилось что угодно ещё, возвращается пустота, и звук идёт к распознаванию
как есть. Эхоподавление — улучшение, а не условие того, что Scott слышит.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

import numpy as np

try:
    from . import echo_cancel
except ImportError:
    import echo_cancel


SAMPLE_RATE = 16000

# Сколько звука накопить, прежде чем мерить задержку.
#
# Не полсекунды, а полсекунды ПЛЮС предел поиска задержки, и это не запас на
# всякий случай. Корреляция ищет образец длиной в полсекунды внутри записи;
# если записи ровно столько же, искать негде — сравнение получается
# единственным, и задержка всегда выходит нулевой. Ровно это и случилось на
# первой проверке: вместо ста двадцати миллисекунд нашлось ноль.
LEARN_SECONDS = 0.5 + echo_cancel.MAX_DELAY_SECONDS


def to_mono_16k(data: np.ndarray, rate: int) -> np.ndarray:
    """
    Привести звук к тому виду, в котором его слышит микрофон.

    Прореживание простое, без сглаживания: опорный сигнал нужен фильтру для
    сравнения, а не для прослушивания, и заметная часть работы здесь была бы
    потрачена впустую.
    """
    сигнал = np.asarray(data, dtype=np.float32)

    if сигнал.ndim > 1:
        сигнал = сигнал.mean(axis=1)

    if rate != SAMPLE_RATE and rate > 0:
        шаг = rate / SAMPLE_RATE
        сколько = int(сигнал.size / шаг)
        if сколько <= 0:
            return np.zeros(0, dtype=np.float32)
        индексы = (np.arange(сколько) * шаг).astype(np.int64)
        сигнал = сигнал[индексы]

    return сигнал.astype(np.float32)


class EchoReference:
    """
    Опорный сигнал с привязкой ко времени.

    Проигрыватель говорит, что начал играть, слушатель спрашивает, что звучало
    в момент записи блока. Между ними — поправка на задержку.
    """

    def __init__(self):
        self._lock = threading.Lock()

        self._signal = np.zeros(0, dtype=np.float32)
        self._started_at = 0.0
        self._playing = False

        # Задержка в отсчётах: запоминается между ответами, пока не сменилось
        # устройство вывода. Мерить её заново на каждой реплике незачем.
        self.delay = 0
        self.delay_known = False

        # Накопленное для замера задержки.
        self._probe_recorded: list[np.ndarray] = []
        self._probe_samples = 0

    # ---- со стороны проигрывателя ----

    def start(self, data: np.ndarray, rate: int) -> None:
        """Scott заговорил: вот что пошло в колонки."""
        сигнал = to_mono_16k(data, rate)

        with self._lock:
            self._signal = сигнал
            self._started_at = time.monotonic()
            self._playing = True
            self._probe_recorded = []
            self._probe_samples = 0

    def stop(self) -> None:
        """Scott договорил."""
        with self._lock:
            self._playing = False
            self._signal = np.zeros(0, dtype=np.float32)

    @property
    def playing(self) -> bool:
        with self._lock:
            return self._playing

    def forget_delay(self) -> None:
        """
        Забыть замеренную задержку.

        Нужно при смене устройства вывода: у других колонок или наушников она
        своя, и прежняя станет не помогать, а мешать.
        """
        with self._lock:
            self.delay = 0
            self.delay_known = False

    # ---- со стороны слушателя ----

    def window(self, length: int, at: Optional[float] = None) -> np.ndarray:
        """
        Что звучало в колонках, пока микрофон писал последний блок.

        Возвращается пустой массив, если Scott молчит или нужного куска нет:
        тогда звук идёт к распознаванию нетронутым.
        """
        if length <= 0:
            return np.zeros(0, dtype=np.float32)

        сейчас = at if at is not None else time.monotonic()

        with self._lock:
            if not self._playing or self._signal.size == 0:
                return np.zeros(0, dtype=np.float32)

            прошло = сейчас - self._started_at
            сигнал = self._signal
            задержка = self.delay

        # Блок только что записан, значит он относится к промежутку,
        # закончившемуся сейчас. Отсюда и отсчитываем назад, а потом ещё на
        # задержку — звук дошёл до микрофона позже, чем ушёл в колонки.
        конец = int(прошло * SAMPLE_RATE) - задержка
        начало = конец - length

        if конец <= 0:
            return np.zeros(0, dtype=np.float32)

        начало = max(0, начало)
        конец = min(сигнал.size, конец)

        if конец <= начало:
            return np.zeros(0, dtype=np.float32)

        кусок = сигнал[начало:конец]

        # Дополняем спереди: в начале ответа опорного сигнала ещё мало.
        if кусок.size < length:
            кусок = np.pad(кусок, (length - кусок.size, 0))

        return кусок

    def learn_delay(self, recorded: np.ndarray) -> bool:
        """
        Замерить задержку по первым блокам ответа.

        Накапливает запись, пока её не наберётся на полсекунды, и сравнивает с
        опорным сигналом. Возвращает True, когда задержка найдена.

        Считать её на каждом ответе незачем: она зависит от устройства вывода,
        а не от фразы.
        """
        with self._lock:
            if self.delay_known or not self._playing or self._signal.size == 0:
                return self.delay_known

            self._probe_recorded.append(np.asarray(recorded, dtype=np.float32))
            self._probe_samples += len(recorded)

            нужно = int(LEARN_SECONDS * SAMPLE_RATE)
            if self._probe_samples < нужно:
                return False

            запись = np.concatenate(self._probe_recorded)
            сигнал = self._signal

        найдено = echo_cancel.estimate_delay(запись, сигнал, SAMPLE_RATE)

        with self._lock:
            self.delay = найдено
            self.delay_known = True
            self._probe_recorded = []
            self._probe_samples = 0

        print(f"🔇 Задержка эха: {найдено / SAMPLE_RATE * 1000:.0f} мс")
        return True


# Одно хранилище на весь backend: проигрыватель и слушатель должны говорить об
# одном и том же звуке.
_reference: Optional[EchoReference] = None


def get_reference() -> EchoReference:
    global _reference
    if _reference is None:
        _reference = EchoReference()
    return _reference
