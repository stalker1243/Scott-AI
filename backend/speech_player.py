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
from pathlib import Path
from typing import Optional

try:
    import numpy as np
    import sounddevice as sd
    from scipy.io import wavfile
    PLAYBACK_AVAILABLE = True
except ImportError:  # pragma: no cover - зависит от окружения
    PLAYBACK_AVAILABLE = False


class SpeechPlayer:
    """Очередь воспроизведения: одна фраза за раз, с возможностью оборвать."""

    def __init__(self) -> None:
        self._queue: "queue.Queue[Optional[str]]" = queue.Queue()
        self._worker: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Поколение растёт при каждом stop(). Файлы, поставленные в очередь до
        # него, воспроизводить уже незачем: человек задал новый вопрос, и
        # старый ответ ему больше не нужен.
        self._generation = 0
        self._playing = False

    # ------------------------------------------------------------------

    def play(self, path: str) -> None:
        """Поставить файл в очередь. Возвращается сразу, не дожидаясь звука."""
        if not PLAYBACK_AVAILABLE or not path:
            return

        with self._lock:
            generation = self._generation
            self._ensure_worker()

        self._queue.put((path, generation, None))

    def play_and_wait(self, path: str, timeout: float = 120.0) -> None:
        """
        Поставить в очередь и дождаться, пока фраза отзвучит.

        Ждать нужно там, где вызывающий код на это рассчитывает: слушатель
        приостанавливает микрофон на время речи, иначе Scott услышит сам себя
        и примет свой ответ за команду.
        """
        if not PLAYBACK_AVAILABLE or not path:
            return

        done = threading.Event()

        with self._lock:
            generation = self._generation
            self._ensure_worker()

        self._queue.put((path, generation, done))
        done.wait(timeout)

    def stop(self) -> None:
        """
        Оборвать всё, что играет и ждёт очереди.

        Вызывается, когда человек заговорил снова: дослушивать ответ на прошлый
        вопрос он всё равно не станет.
        """
        if not PLAYBACK_AVAILABLE:
            return

        with self._lock:
            self._generation += 1

        # Чистим очередь, не трогая поток: он сам увидит смену поколения.
        while True:
            try:
                item = self._queue.get_nowait()
                if item is not None and item[2] is not None:
                    # Тот, кто ждал эту фразу, должен продолжить работу, а не
                    # висеть до истечения таймаута.
                    item[2].set()
                self._queue.task_done()
            except queue.Empty:
                break

        try:
            sd.stop()
        except Exception:
            pass

    @property
    def busy(self) -> bool:
        """Звучит ли что-то прямо сейчас (или ждёт очереди)."""
        return self._playing or not self._queue.empty()

    # ------------------------------------------------------------------

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
                self._queue.task_done()
                return

            path, generation, done = item
            try:
                # Файл из устаревшего поколения пропускаем молча: он был
                # ответом на вопрос, который человек уже перебил.
                if generation == self._generation:
                    self._play_file(path)
            except Exception as e:
                print(f"❌ Ошибка воспроизведения: {e}")
            finally:
                self._playing = False
                if done is not None:
                    done.set()
                self._queue.task_done()

    def _play_file(self, path: str) -> None:
        file = Path(path)
        if not file.exists():
            return

        rate, data = wavfile.read(str(file))

        # Silero отдаёт целочисленный сигнал, sounddevice ждёт float в
        # диапазоне [-1, 1]. Без нормализации звук уходит в хрип.
        if data.dtype.kind in "iu":
            info = np.iinfo(data.dtype)
            data = data.astype(np.float32) / max(abs(info.min), info.max)

        self._playing = True
        sd.play(data, rate)
        sd.wait()


# Один проигрыватель на весь backend: две очереди означали бы ровно ту
# многоголосицу, ради которой всё это и написано.
_player: Optional[SpeechPlayer] = None


def get_player() -> SpeechPlayer:
    global _player
    if _player is None:
        _player = SpeechPlayer()
    return _player
