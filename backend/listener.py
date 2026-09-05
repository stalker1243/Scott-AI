"""
Постоянное прослушивание микрофона с активацией по имени.

До сих пор голосового ввода в проекте не было вовсе: `/speech_to_text` умел
распознать присланный файл, но записывать звук было некому — ни backend, ни
лаунчер микрофон не трогали. Система активации по имени (`voice_name_trigger`)
при этом была написана давно и лежала мёртвым кодом.

Здесь эти две половины соединяются. Модуль слушает микрофон, сам решает, где
во входящем потоке началась и закончилась фраза, отдаёт её распознавателю и,
если человек назвал Scott по имени, выполняет команду.

Устроено на трёх нитях, и это не усложнение ради усложнения:

* **Захват** только складывает блоки в очередь — задерживать его нельзя, иначе
  звук начнёт теряться кусками.
* **Разбор** собирает из блоков фразы по уровню громкости.
* **Обработка** распознаёт и выполняет. Whisper занимает сотни миллисекунд, и
  делать это в потоке захвата означало бы глохнуть на время каждой команды.

Порог громкости не константа: тихий микрофон в наушниках и открытый микрофон
в комнате дают разный фон, поэтому уровень тишины замеряется при старте и
дальше подстраивается.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import numpy as np

try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except Exception:  # pragma: no cover — на машине без звуковой подсистемы
    sd = None
    HAS_SOUNDDEVICE = False


# Whisper обучен на 16 кГц — записывать выше смысла нет, а ниже нельзя.
SAMPLE_RATE = 16000

# Блок в 30 мс: достаточно мелкий, чтобы вовремя заметить начало речи, и
# достаточно крупный, чтобы не гонять поток впустую.
BLOCK_MS = 30
BLOCK_SIZE = SAMPLE_RATE * BLOCK_MS // 1000


@dataclass
class ListenerConfig:
    """Настройки прослушивания. Значения подобраны под обычную речь."""

    # Во сколько раз громче фона должен быть звук, чтобы считаться речью.
    # Множитель, а не абсолютный порог: фон у разных микрофонов различается на
    # порядки, и одно и то же число было бы то слишком строгим, то бесполезным.
    speech_threshold: float = 3.0

    # Ниже этого уровня не реагируем даже при тихом фоне — иначе Scott начнёт
    # распознавать шорохи в полной тишине.
    absolute_floor: float = 0.006

    # Сколько подряд блоков должны быть громкими, чтобы признать начало речи.
    # Отсекает щелчки и одиночные стуки по столу.
    onset_blocks: int = 3

    # Пауза, после которой фраза считается законченной. Меньше — Scott будет
    # обрывать на вдохе, больше — заметно задумываться перед ответом.
    silence_to_end: float = 0.8

    # Границы длины фразы: слишком короткое — случайный звук, слишком
    # длинное — разговор не с ассистентом.
    min_phrase: float = 0.35
    max_phrase: float = 15.0

    # Хвост звука перед началом речи: человек начинает говорить раньше, чем громкость
    # переваливает порог, и без этого запаса теряется первый слог — как раз тот,
    # в котором чаще всего и звучит имя.
    preroll: float = 0.4

    device: Optional[int] = None


@dataclass
class ListenerStats:
    """Что происходило — для вкладки диагностики и отладки."""

    phrases_heard: int = 0
    triggered: int = 0
    ignored: int = 0
    last_text: str = ""
    last_error: str = ""
    noise_floor: float = 0.0
    started_at: float = 0.0
    recent: List[str] = field(default_factory=list)


class VoiceListener:
    """
    Слушает микрофон и выполняет команды, обращённые к Scott по имени.

    Распознавание и обработку модуль не реализует — они передаются функциями.
    Так его можно проверить без микрофона и без Whisper, скормив заранее
    записанный звук через `feed`.
    """

    def __init__(
        self,
        transcribe: Callable[[np.ndarray], str],
        handle_command: Callable[[str], None],
        check_trigger: Optional[Callable[[str], object]] = None,
        config: Optional[ListenerConfig] = None,
    ):
        self.transcribe = transcribe
        self.handle_command = handle_command
        self.check_trigger = check_trigger
        self.config = config or ListenerConfig()

        self.stats = ListenerStats()
        self._running = False
        self._blocks: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=200)
        self._phrases: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=8)
        self._threads: List[threading.Thread] = []
        self._stream = None
        self._lock = threading.Lock()

        self._noise_floor = self.config.absolute_floor
        # Пока Scott говорит, входящий звук не разбирается: иначе он слышит
        # собственный ответ из колонок и принимает его за новую фразу.
        self._suspended = False

    # ==================== Управление ====================

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> dict:
        if self._running:
            return {"success": True, "message": "Scott уже слушает"}
        if not HAS_SOUNDDEVICE:
            return {"success": False, "message": "Библиотека sounddevice не установлена — записывать звук нечем"}

        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=BLOCK_SIZE,
                device=self.config.device,
                callback=self._on_audio,
            )
            self._stream.start()
        except Exception as e:
            self._stream = None
            return {"success": False, "message": f"Не удалось открыть микрофон: {e}"}

        self._running = True
        self.stats = ListenerStats(started_at=time.time(), noise_floor=self._noise_floor)

        self._threads = [
            threading.Thread(target=self._segment_loop, name="scott-segment", daemon=True),
            threading.Thread(target=self._process_loop, name="scott-process", daemon=True),
        ]
        for thread in self._threads:
            thread.start()

        print("🎧 Scott слушает микрофон")
        return {"success": True, "message": "Scott слушает"}

    def stop(self) -> dict:
        if not self._running:
            return {"success": True, "message": "Scott и так не слушает"}

        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                print(f"⚠️ Ошибка при остановке потока: {e}")
            self._stream = None

        # Будим разборщик, чтобы он вышел из ожидания блока.
        try:
            self._blocks.put_nowait(np.zeros(BLOCK_SIZE, dtype=np.float32))
        except queue.Full:
            pass

        print("🎧 Scott перестал слушать")
        return {"success": True, "message": "Scott больше не слушает"}

    # ==================== Собственный голос ====================

    def suspend(self) -> None:
        """
        Перестать разбирать входящий звук, пока Scott говорит сам.

        Микрофон слышит колонки: собственный ответ Scott возвращается к нему же
        как новая фраза. На живой проверке это выглядело так — он произнёс
        ответ, а следующей строкой в логе появилось «Мимо: "Попробую открыть
        Google Chrome"», то есть он распознал сам себя. Пока в ответе не звучит
        его имя, дело кончается лишней работой Whisper, но стоит Scott сказать
        «Скотт» — и он начнёт разговаривать сам с собой без остановки.

        Поток не закрывается: открывать микрофон заново на каждую реплику
        долго и чревато щелчками. Блоки просто перестают складываться в очередь.
        """
        self._suspended = True

    def resume(self) -> None:
        """
        Снова слушать.

        Очередь блоков очищается: за время ответа там накопился собственный
        голос Scott, и разбирать его теперь незачем.
        """
        while True:
            try:
                self._blocks.get_nowait()
            except queue.Empty:
                break
        self._suspended = False

    @property
    def is_suspended(self) -> bool:
        return self._suspended

    def status(self) -> dict:
        return {
            "listening": self._running,
            "speaking": self._suspended,
            "available": HAS_SOUNDDEVICE,
            "noise_floor": round(self._noise_floor, 5),
            "phrases_heard": self.stats.phrases_heard,
            "triggered": self.stats.triggered,
            "ignored": self.stats.ignored,
            "last_text": self.stats.last_text,
            "last_error": self.stats.last_error,
            "recent": list(self.stats.recent[-10:]),
            "uptime_sec": round(time.time() - self.stats.started_at, 1) if self.stats.started_at else 0,
        }

    # ==================== Захват ====================

    def _on_audio(self, indata, frames, time_info, status) -> None:
        """
        Callback звукового потока. Обязан быть быстрым.

        Всё, что здесь делается, — копирование блока в очередь. Любая
        задержка (распознавание, запись на диск, печать) приводит к пропускам
        в записи, которые потом слышны как проглоченные слоги.
        """
        if status:
            self.stats.last_error = str(status)
        if self._suspended:
            return
        try:
            self._blocks.put_nowait(indata[:, 0].copy())
        except queue.Full:
            # Очередь переполнена — значит разбор не успевает. Лучше потерять
            # блок, чем копить задержку, которая уже никогда не рассосётся.
            pass

    def feed(self, samples: np.ndarray) -> None:
        """
        Подать звук напрямую, минуя микрофон.

        Нужно для проверок: без этого модуль нельзя было бы протестировать
        нигде, кроме машины с микрофоном и живым человеком рядом.
        """
        for start in range(0, len(samples), BLOCK_SIZE):
            block = samples[start:start + BLOCK_SIZE]
            if len(block) < BLOCK_SIZE:
                block = np.pad(block, (0, BLOCK_SIZE - len(block)))
            self._blocks.put(block.astype(np.float32))

    # ==================== Разбор на фразы ====================

    @staticmethod
    def _level(block: np.ndarray) -> float:
        """Громкость блока — среднеквадратичное значение."""
        return float(np.sqrt(np.mean(np.square(block)))) if len(block) else 0.0

    def _segment_loop(self) -> None:
        """
        Собрать из потока блоков законченные фразы.

        Речь начинается, когда несколько блоков подряд заметно громче фона, и
        заканчивается, когда тишина держится дольше паузы. Пока речи нет, фон
        медленно подстраивается — иначе включённый вентилятор или шум улицы
        через полчаса сделали бы порог бессмысленным.
        """
        preroll_blocks = max(1, int(self.config.preroll * 1000 / BLOCK_MS))
        silence_blocks = max(1, int(self.config.silence_to_end * 1000 / BLOCK_MS))
        max_blocks = int(self.config.max_phrase * 1000 / BLOCK_MS)
        min_blocks = max(1, int(self.config.min_phrase * 1000 / BLOCK_MS))

        preroll: List[np.ndarray] = []
        phrase: List[np.ndarray] = []
        loud_streak = 0
        silence_streak = 0
        loud_in_phrase = 0
        in_speech = False

        while self._running:
            try:
                block = self._blocks.get(timeout=0.5)
            except queue.Empty:
                continue

            level = self._level(block)
            threshold = max(self._noise_floor * self.config.speech_threshold, self.config.absolute_floor)
            loud = level > threshold

            if not in_speech:
                # Фон обновляем только по тишине и очень медленно: резкий
                # пересчёт по громкому блоку поднял бы порог так, что речь
                # перестала бы его преодолевать.
                if not loud:
                    self._noise_floor = 0.95 * self._noise_floor + 0.05 * level
                    self.stats.noise_floor = self._noise_floor

                preroll.append(block)
                if len(preroll) > preroll_blocks:
                    preroll.pop(0)

                loud_streak = loud_streak + 1 if loud else 0
                if loud_streak >= self.config.onset_blocks:
                    in_speech = True
                    phrase = list(preroll)
                    preroll.clear()
                    silence_streak = 0
                    loud_in_phrase = loud_streak
            else:
                phrase.append(block)
                if loud:
                    loud_in_phrase += 1
                silence_streak = 0 if loud else silence_streak + 1

                too_long = len(phrase) >= max_blocks
                if silence_streak >= silence_blocks or too_long:
                    in_speech = False
                    loud_streak = 0
                    # Считаются именно ГРОМКИЕ блоки, а не длина буфера: в него
                    # входят запас перед фразой и пауза после неё, вместе почти
                    # полторы секунды. Проверка по длине буфера пропускала любой
                    # щелчок — тот выглядел как фраза за счёт этой тишины.
                    if loud_in_phrase >= min_blocks:
                        audio = np.concatenate(phrase)
                        try:
                            self._phrases.put_nowait(audio)
                        except queue.Full:
                            self.stats.last_error = "Не успеваю обрабатывать — фраза пропущена"
                    phrase = []
                    loud_in_phrase = 0

    # ==================== Распознавание и выполнение ====================

    def _process_loop(self) -> None:
        while self._running:
            try:
                audio = self._phrases.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                text = (self.transcribe(audio) or "").strip()
            except Exception as e:
                self.stats.last_error = f"Распознавание не удалось: {e}"
                print(f"⚠️ {self.stats.last_error}")
                continue

            if not text:
                continue

            with self._lock:
                self.stats.phrases_heard += 1
                self.stats.last_text = text
                self.stats.recent.append(text)
                del self.stats.recent[:-20]

            self._dispatch(text)

    def _dispatch(self, text: str) -> None:
        """
        Решить, обращались ли к Scott, и выполнить команду.

        Без имени команда игнорируется молча: Scott слышит всю комнату, и
        реагировать на любой разговор рядом — худшее, что он может делать.
        """
        command = text
        if self.check_trigger is not None:
            result = self.check_trigger(text)
            if not getattr(result, "has_trigger", False):
                self.stats.ignored += 1
                print(f"🔇 Мимо: «{text}»")
                return
            command = (getattr(result, "command_text", "") or "").strip()
            if not command:
                # Позвали по имени, но ничего не попросили.
                self.stats.triggered += 1
                print("🎧 Scott слышит своё имя, но команды не было")
                return

        self.stats.triggered += 1
        print(f"🎤 Команда: «{command}»")
        try:
            self.handle_command(command)
        except Exception as e:
            self.stats.last_error = f"Команда не выполнена: {e}"
            print(f"⚠️ {self.stats.last_error}")


def list_input_devices() -> List[dict]:
    """Микрофоны, доступные в системе, — чтобы можно было выбрать нужный."""
    if not HAS_SOUNDDEVICE:
        return []
    devices = []
    try:
        default = sd.default.device[0]
        for index, info in enumerate(sd.query_devices()):
            if info.get("max_input_channels", 0) > 0:
                devices.append({
                    "index": index,
                    "name": info.get("name", ""),
                    "channels": info.get("max_input_channels", 0),
                    "default": index == default,
                })
    except Exception as e:
        print(f"⚠️ Не удалось получить список устройств: {e}")
    return devices
