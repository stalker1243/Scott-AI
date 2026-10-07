"""
Воспроизведение речи: по одной фразе за раз.

Раньше каждый ответ проигрывался сам по себе, в своём потоке: Scott запускал
PowerShell с `SoundPlayer.PlaySync()` и не знал, что в этот момент играет
что-то ещё. Если человек задавал несколько вопросов подряд, ответы начинали
звучать одновременно — на слух получался набор слов, выпаливаемых сразу все.

Здесь этого не может быть по устройству: есть одна очередь и один поток,
который её разбирает. Новая просьба говорить не перебивает предыдущую, а
становится следующей; а когда человек задаёт новый вопрос, старую очередь
можно оборвать целиком — `stop()`.

Звук выводится через sounddevice, а не через PowerShell: запуск процесса стоил
двести-четыреста миллисекунд на каждую фразу, и прервать его было нечем.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import numpy as np
    import sounddevice as sd
    from scipy.io import wavfile
    PLAYBACK_AVAILABLE = True
except ImportError:  # pragma: no cover - зависит от окружения
    PLAYBACK_AVAILABLE = False


# Some drivers keep a blocking write alive after abort(). Bound that call so
# the queue can release cancelled files and start a new reply promptly.
STREAM_WRITE_SECONDS = .1


def _audio_settings():
    """
    Настройки звука, если модуль доступен.

    Ввозится внутри функций, а не сверху файла: проигрыватель должен работать и
    там, где настроек нет вовсе, — например, в тестах, которые проверяют саму
    очередь и ничего не знают про хранилище.
    """
    try:
        try:
            from . import audio_settings
        except ImportError:
            import audio_settings
        return audio_settings
    except Exception:
        return None


def _muted() -> bool:
    """Просил ли человек молчать."""
    settings = _audio_settings()
    return bool(settings.is_quiet()) if settings else False


def _volume() -> float:
    """Множитель громкости: 1.0 — как синтезировано."""
    settings = _audio_settings()
    return settings.get_volume() if settings else 1.0


def _output_device():
    """Номер устройства вывода или None — тогда играем в системное."""
    settings = _audio_settings()
    return settings.get_output_device() if settings else None


class _Completion(threading.Event):
    def __init__(self, player=None, generation=None, on_finished=None):
        super().__init__()
        self.error = None
        self.cancelled = False
        self._player = player
        self._generation = generation
        self._on_finished = on_finished
        self.released = threading.Event()

    def result(self, timeout=120.0):
        if not self.wait(timeout):
            if self._player is not None:
                self._player.stop(generation=self._generation)
            raise TimeoutError('Превышено время ожидания воспроизведения')
        if self.error is not None:
            raise self.error
        return not self.cancelled

    def finish(self):
        # Cancellation can wake a caller before an in-flight read/write ends.
        # Release owned files only when the queue owner has finished that job.
        callback, self._on_finished = self._on_finished, None
        try:
            if callback is not None:
                callback()
        finally:
            self.released.set()
            self.set()


@dataclass
class _StreamBlock:
    path: str
    token: object
    last: bool


@dataclass
class _OutputSession:
    token: object
    stream: object
    next_at: float = 0.
    cancelled: bool = False
    closed: bool = False


@dataclass
class _CloseOutput:
    session: _OutputSession


class SpeechPlayer:
    """Очередь воспроизведения: одна фраза за раз, с возможностью оборвать."""

    def __init__(self) -> None:
        self._queue: queue.Queue = queue.Queue()
        self._worker: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Поколение растёт при каждом stop(). Файлы, поставленные в очередь до
        # него, воспроизводить уже незачем: человек задал новый вопрос, и
        # старый ответ ему больше не нужен.
        self._generation = 0
        self._playing = False
        self._active_done = None
        self._active_generation = None
        self._output_session = None
        self._stream_stats = dict(opened=0, blocks=0, underflows=0)

    # ------------------------------------------------------------------

    def _enqueue(self, item, force=False, generation=None, on_finished=None):
        if not PLAYBACK_AVAILABLE or not item:
            raise RuntimeError('Воспроизведение звука недоступно')
        if on_finished is not None and not callable(on_finished):
            raise ValueError('Expected playback cleanup callback')
        if _muted() and not force:
            return None
        with self._lock:
            if generation is not None and generation != self._generation:
                return None
            generation = self._generation
            done = _Completion(self, generation, on_finished)
            self._ensure_worker()
            self._queue.put((item, generation, done))
        return done

    def queue_file(self, path, force=False, generation=None, on_finished=None):
        """Return a playback receipt without waiting for the audio device."""
        return self._enqueue(path, force, generation, on_finished)

    def queue_stream(self, path, token, last=False, force=False, generation=None, on_finished=None):
        if not path:
            raise RuntimeError('Воспроизведение звука недоступно')
        if token is None or not isinstance(last, bool):
            raise ValueError('Invalid playback stream')
        return self._enqueue(_StreamBlock(path, token, last), force, generation, on_finished)

    def play(self, path: str, force: bool = False, generation=None) -> bool:
        """
        Поставить файл в очередь. Возвращается сразу, не дожидаясь звука.

        `force` пропускает тихий режим — им пользуется только прослушивание
        голоса в настройках: человек нажал кнопку «Прослушать» и ждёт звука
        именно сейчас, что бы ни стояло в общих настройках.
        """
        return self.queue_file(path, force, generation) is not None

    def play_and_wait(self, path: str, timeout: float = 120.0, force: bool = False, generation=None) -> bool:
        """
        Поставить в очередь и дождаться, пока фраза отзвучит.

        Ждать нужно там, где вызывающий код на это рассчитывает: слушатель
        приостанавливает микрофон на время речи, иначе Scott услышит сам себя
        и примет свой ответ за команду.
        """
        done = self.queue_file(path, force, generation)
        return done.result(timeout) if done is not None else False

    def play_stream(self, path, token, last=False, force=False, generation=None, timeout=120.0) -> bool:
        """Queue PCM blocks into one device stream; drain only the last block."""
        done = self.queue_stream(path, token, last, force, generation)
        if done is None:
            return False
        return done.result(timeout) if last else True

    @property
    def stream_stats(self):
        with self._lock:
            return dict(self._stream_stats)

    def stop(self, generation=None) -> None:
        """
        Оборвать всё, что играет и ждёт очереди.

        Вызывается, когда человек заговорил снова: дослушивать ответ на прошлый
        вопрос он всё равно не станет.
        """
        if not PLAYBACK_AVAILABLE:
            return

        discarded = []
        with self._lock:
            if generation is not None and generation != self._generation:
                return
            self._generation += 1
            if self._active_done is not None:
                self._active_done.cancelled = True
                self._active_done.set()

            # Queue insertion and stop share this lock: a new response cannot
            # be drained accidentally while cancelling the previous one.
            closing = []
            while True:
                try:
                    item = self._queue.get_nowait()
                    if item is not None and isinstance(item[0], _CloseOutput):
                        closing.append(item[0])
                    if item is not None and item[2] is not None:
                        item[2].cancelled = True
                        item[2].set()
                        discarded.append(item[2])
                    self._queue.task_done()
                except queue.Empty:
                    break
            try:
                sd.stop()
            except Exception:
                pass
            session, self._output_session = self._output_session, None
            if session is not None:
                session.cancelled = True
                try:
                    session.stream.abort()
                except Exception:
                    pass
                # The owner thread closes after any in-flight write has ended.
                closing.append(_CloseOutput(session))
            # A second cancellation must retain cleanup queued by the first.
            for close in closing:
                self._queue.put((close, self._generation, None))
        for done in discarded:
            self._finish_job(done)

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    @property
    def busy(self) -> bool:
        """Звучит ли что-то прямо сейчас (или ждёт очереди)."""
        return self._playing or self._output_session is not None or not self._queue.empty()

    # ------------------------------------------------------------------

    @staticmethod
    def _finish_job(done):
        try:
            done.finish()
        except Exception:
            # Cleanup failure must not kill the single playback worker.
            done.set()

    def _ensure_worker(self) -> None:
        """Поток-разборщик запускается лениво и живёт до конца работы."""
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(
                target=self._run, name="speech-player", daemon=True
            )
            self._worker.start()

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                try:
                    self._close_output(self._output_session, cancel=True)
                except Exception:
                    pass
                finally:
                    self._queue.task_done()
                return

            path, generation, done = item
            if isinstance(path, _CloseOutput):
                try:
                    self._close_output(path.session, cancel=True)
                except Exception:
                    pass
                finally:
                    self._queue.task_done()
                continue
            try:
                # Файл из устаревшего поколения пропускаем молча: он был
                # ответом на вопрос, который человек уже перебил.
                with self._lock:
                    current = generation == self._generation
                    self._active_generation = generation
                    self._active_done = done
                if current:
                    if isinstance(path, _StreamBlock):
                        self._play_stream_block(path)
                    else:
                        self._close_output(self._output_session)
                        self._play_file(path)
                elif done is not None:
                    done.cancelled = True
            except Exception as e:
                with self._lock:
                    cancelled = generation != self._generation
                if not cancelled:
                    print(f"❌ Ошибка воспроизведения: {e}")
                if done is not None and not cancelled:
                    done.error = e
                self.stop(generation=generation)
            finally:
                self._playing = False
                with self._lock:
                    if done is not None and generation != self._generation:
                        done.cancelled = True
                    self._active_done = None
                    self._active_generation = None
                if done is not None:
                    self._finish_job(done)
                self._queue.task_done()

    @staticmethod
    def _read_audio(path):
        file = Path(path)
        if not file.exists():
            raise FileNotFoundError(path)

        rate, data = wavfile.read(str(file))

        # Silero отдаёт целочисленный сигнал, sounddevice ждёт float в
        # диапазоне [-1, 1]. Без нормализации звук уходит в хрип.
        if data.dtype.kind in "iu":
            info = np.iinfo(data.dtype)
            data = data.astype(np.float32) / max(abs(info.min), info.max)

        # Громкость — простое умножение волны. Синтезатор отдаёт готовый звук
        # и своей регулировки не имеет, а системный микшер к нему не применить:
        # там громкость общая на всё приложение, включая звуки самой ОС.
        volume = _volume()
        if volume < 0.999:
            data = data * volume
        return rate, data

    def _close_output(self, session, cancel=False):
        if session is None or session.closed:
            return
        try:
            if cancel or session.cancelled:
                session.stream.abort()
            else:
                session.stream.stop()
        finally:
            try:
                session.stream.close()
            finally:
                session.closed = True
                with self._lock:
                    if self._output_session is session:
                        self._output_session = None
                try:
                    self._echo_reference().stop()
                except Exception:
                    pass

    def _play_stream_block(self, block):
        rate, data = self._read_audio(block.path)
        if rate != 24000 or data.ndim != 1 or not len(data):
            raise ValueError('Invalid Scott playback block')
        session = self._output_session
        if session is not None and session.token is not block.token:
            self._close_output(session)
            session = None
        if session is None:
            stream = sd.OutputStream(samplerate=rate, channels=1, dtype='float32', device=_output_device())
            session = _OutputSession(block.token, stream)
            with self._lock:
                if self._active_generation != self._generation:
                    stream.close()
                    return
                self._output_session = session
                try:
                    stream.start()
                    self._stream_stats['opened'] += 1
                except Exception:
                    session.cancelled = True
                    # Cleanup below must happen without re-entering this lock.
                    failed = True
                else:
                    failed = False
            if failed:
                self._close_output(session, cancel=True)
                raise RuntimeError('Не удалось открыть поток звука')
            try:
                self._echo_reference().start_stream()
            except Exception:
                pass
        with self._lock:
            if self._active_generation != self._generation or session.cancelled:
                return
        self._playing = True
        start = max(time.monotonic(), session.next_at)
        session.next_at = start + len(data)/rate
        try:
            self._echo_reference().stream_block(data, rate, start)
        except Exception:
            pass
        pcm = np.ascontiguousarray(data, dtype=np.float32)
        stride = max(1, round(rate*STREAM_WRITE_SECONDS))
        underflowed = False
        for offset in range(0, len(pcm), stride):
            with self._lock:
                if self._active_generation != self._generation or session.cancelled:
                    return
            # Keep one device stream and exact PCM order. Cancellation can now
            # stop between short writes even when abort doesn't wake a driver.
            underflowed = bool(session.stream.write(pcm[offset:offset+stride])) or underflowed
        with self._lock:
            self._stream_stats['blocks'] += 1
            self._stream_stats['underflows'] += int(bool(underflowed))
        if block.last:
            self._close_output(session)

    def _play_file(self, path: str) -> None:
        rate, data = self._read_audio(path)

        # Отдаём тот же звук эхоподавлению: оно вычтет его из того, что
        # услышит микрофон. В этом наше преимущество перед обычным
        # эхоподавлением — ему приходится перехватывать звук с устройства
        # вывода, а мы знаем его заранее.
        #
        # Сообщаем ровно перед sd.play: отсюда и отсчитывается время, и лишние
        # миллисекунды между «сказали» и «заиграло» станут ошибкой выравнивания.
        try:
            self._echo_reference().start(data, rate)
        except Exception:
            # Эхоподавление — улучшение, а не условие того, что Scott говорит.
            pass

        self._playing = True
        try:
            device = _output_device()
            with self._lock:
                if self._active_generation != self._generation:
                    return
                sd.play(data, rate, device=device)
            sd.wait()
        finally:
            try:
                self._echo_reference().stop()
            except Exception:
                pass

    @staticmethod
    def _echo_reference():
        """Хранилище опорного сигнала. Импорт внутри — ради порядка загрузки."""
        try:
            from . import echo_reference
        except ImportError:
            import echo_reference

        return echo_reference.get_reference()


# Один проигрыватель на весь backend: две очереди означали бы ровно ту
# многоголосицу, ради которой всё это и написано.
_player: Optional[SpeechPlayer] = None
_PLAYER_LOCK = threading.Lock()


def get_player() -> SpeechPlayer:
    global _player
    with _PLAYER_LOCK:
        if _player is None:
            _player = SpeechPlayer()
    return _player
