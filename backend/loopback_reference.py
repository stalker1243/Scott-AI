"""
Опорный сигнал из колонок: всё, что слышит комната.

ЗАЧЕМ. Прежнее эхоподавление вычитало из микрофона только собственную речь
Scott — сигнал брался у проигрывателя. Это защищает от «услышал сам себя», но
не от всего остального, что звучит из тех же колонок.

18 сентября это вышло наружу: в журнале услышанного нашлась команда, которой
человек не говорил, — «Скотт, открой программу. Скотт, закрой программу.».
Сказал её чужой помощник из динамиков: рядом шёл разговор в Discord, и
собеседник проверял свою копию теми же словами. В том же журнале половина
записей оказалась обрывками чужой речи: видео, разговоры, музыка. Scott
добросовестно всё это распознавал.

ЧТО ДЕЛАЕТ ЭТОТ МОДУЛЬ. Непрерывно записывает то, что уходит в колонки
(loopback), и отдаёт кусок, звучавший в нужный момент. Дальше — то же
вычитание, что и раньше: `echo_cancel` убирает из микрофонного сигнала всё,
что нашлось в опорном.

ПОЧЕМУ ОТДЕЛЬНАЯ БИБЛИОТЕКА. sounddevice, которым Scott пишет микрофон, не
умеет открывать устройство вывода на запись: в его `WasapiSettings` нет
loopback. `soundcard` умеет — через тот же WASAPI, без своих драйверов.

ПРИ ЛЮБОЙ БЕДЕ — МОЛЧАНИЕ. Нет библиотеки, нет устройства, отказал захват —
возвращается пустота, и Scott работает как прежде, вычитая только собственную
речь. Эхоподавление остаётся улучшением, а не условием того, что он слышит.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

import numpy as np

SAMPLE_RATE = 16000

# Сколько звука держать наготове.
#
# Две секунды — с запасом на самую долгую задержку тракта (колонки, воздух,
# буферы драйвера) и на длину блока, который спрашивает слушатель. Больше
# держать незачем: всё, что старше, уже не с чем сопоставлять.
BUFFER_SECONDS = 2.0

# Размер блока захвата. Меньше — чаще просыпается поток, больше — грубее
# привязка ко времени.
BLOCK = 1024


class LoopbackReference:
    """
    Кольцевая запись того, что звучит в колонках.

    Живёт в отдельном потоке: захват блокирующий, а слушатель в это время
    должен разбирать микрофон.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._buffer = np.zeros(int(SAMPLE_RATE * BUFFER_SECONDS), dtype=np.float32)

        # Момент, которому соответствует конец буфера.
        self._filled_at = 0.0

        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._error = ""
        self._device_name = ""

    # ---- жизнь ----

    @property
    def available(self) -> bool:
        return self._running

    @property
    def device_name(self) -> str:
        return self._device_name

    @property
    def last_error(self) -> str:
        return self._error

    def start(self) -> bool:
        """
        Начать слушать колонки. Возвращает True, если получилось.

        Неудача здесь — обычное дело: библиотеки может не быть, устройство
        может не поддерживать запись с вывода. Тогда Scott работает как прежде.
        """
        if self._running:
            return True

        try:
            import soundcard
        except ImportError:
            self._error = "нет библиотеки soundcard"
            return False

        try:
            динамик = soundcard.default_speaker()
            петля = soundcard.get_microphone(str(динамик.name), include_loopback=True)
        except Exception as e:
            self._error = f"не нашёл устройство вывода: {e}"
            return False

        self._device_name = str(getattr(динамик, "name", ""))[:60]
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, args=(петля,), daemon=True, name="scott-loopback")
        self._thread.start()

        return True

    def stop(self) -> None:
        self._running = False

    # ---- захват ----

    def _loop(self, петля) -> None:
        try:
            with петля.recorder(samplerate=SAMPLE_RATE, channels=1, blocksize=BLOCK) as запись:
                while self._running:
                    блок = запись.record(numframes=BLOCK)
                    self._push(np.asarray(блок, dtype=np.float32).reshape(-1))
        except Exception as e:
            # Устройство могло исчезнуть — например, отключили наушники.
            self._error = f"захват прервался: {e}"
            self._running = False

    def _push(self, блок: np.ndarray) -> None:
        if блок.size == 0:
            return

        with self._lock:
            if блок.size >= self._buffer.size:
                self._buffer = блок[-self._buffer.size:].copy()
            else:
                self._buffer = np.concatenate([self._buffer[блок.size:], блок])

            self._filled_at = time.monotonic()

    # ---- выдача ----

    def window(self, length: int, at: Optional[float] = None, delay: int = 0) -> np.ndarray:
        """
        Что звучало в колонках, пока микрофон писал последний блок.

        `delay` — на сколько отсчётов звук отстал: он проходит через колонки,
        воздух и буферы драйвера. Для loopback эта задержка меньше, чем для
        сигнала, взятого у проигрывателя (тот отсчитывается от «начали играть»,
        а здесь — от «услышали на выходе»), но не нулевая.
        """
        if length <= 0 or not self._running:
            return np.zeros(0, dtype=np.float32)

        сейчас = at if at is not None else time.monotonic()

        with self._lock:
            буфер = self._buffer
            записано_в = self._filled_at

        if записано_в <= 0:
            return np.zeros(0, dtype=np.float32)

        # Сколько прошло с последнего блока захвата — на столько сместился
        # конец интересующего куска.
        отставание = int(max(0.0, сейчас - записано_в) * SAMPLE_RATE)

        конец = буфер.size - отставание - delay
        начало = конец - length

        if конец <= 0:
            return np.zeros(0, dtype=np.float32)

        начало = max(0, начало)
        конец = min(буфер.size, конец)

        if конец <= начало:
            return np.zeros(0, dtype=np.float32)

        кусок = буфер[начало:конец]

        if кусок.size < length:
            кусок = np.pad(кусок, (length - кусок.size, 0))

        return кусок

    def is_quiet(self, threshold: float = 1e-4) -> bool:
        """
        Молчат ли колонки прямо сейчас.

        Полезно само по себе: если в колонках тишина, вычитать нечего, и можно
        не тратить работу.
        """
        with self._lock:
            хвост = self._buffer[-SAMPLE_RATE // 4:]

        return float(np.sqrt(np.mean(хвост ** 2))) < threshold


# ==================== Один захват на процесс ====================

_reference: Optional[LoopbackReference] = None
_lock = threading.Lock()


def get_loopback() -> LoopbackReference:
    global _reference

    with _lock:
        if _reference is None:
            _reference = LoopbackReference()

    return _reference
