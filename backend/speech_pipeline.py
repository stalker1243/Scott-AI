"""Own queued WAV copies until the playback worker releases every block."""
from pathlib import Path
import shutil
import tempfile
import threading
import time

try:
    from .speech_buffer import join_wavs
    from .scott_voice_process import VoiceProcessError
except ImportError:
    from speech_buffer import join_wavs
    from scott_voice_process import VoiceProcessError


class QueuedSpeech:
    """One phrase: at most 128 jobs, with cleanup after reads and cancellation."""
    def __init__(self, player, generation, force=False):
        self.player = player
        self.generation = generation
        self.force = force
        self.token = object()
        self.ticket = None
        self._directory = None
        self._lock = threading.Lock()
        self._pending = 0
        self._count = 0
        self._sealed = False

    def submit(self, paths, last, use_stream):
        if self._sealed or self.ticket is not None or self._count >= 128 or not paths:
            raise ValueError('Invalid queued speech sequence')
        if self._directory is None:
            self._directory = tempfile.TemporaryDirectory(prefix='.scott-prefetch-',
                dir=Path(paths[0]).parent, ignore_cleanup_errors=True)
        path = Path(self._directory.name)/f'{self._count:03}.wav'
        if len(paths)>1:
            join_wavs(paths, path)
        else:
            shutil.copyfile(paths[0], path)
        self._count += 1
        with self._lock:
            self._pending += 1
        def release():
            try:
                path.unlink(missing_ok=True)
            finally:
                with self._lock:
                    self._pending -= 1
                    self._cleanup()
        try:
            options = dict(force=self.force,generation=self.generation,on_finished=release)
            if use_stream:
                ticket = self.player.queue_stream(str(path),self.token,last=last,**options)
            else:
                ticket = self.player.queue_file(str(path),**options)
        except Exception:
            release()
            raise
        if ticket is None:
            release()
            raise VoiceProcessError('cancelled')
        if last:
            self.ticket = ticket
        return True

    def seal(self):
        with self._lock:
            self._sealed = True
            self._cleanup()

    def _cleanup(self):
        if self._sealed and not self._pending and self._directory is not None:
            self._directory.cleanup()
            self._directory = None

    def wait(self, current, timeout=120.):
        if self.ticket is None:
            raise VoiceProcessError('invalid_protocol')
        deadline = time.monotonic()+timeout
        while not self.ticket.wait(.05):
            current()
            if time.monotonic()>=deadline:
                self.player.stop(generation=self.generation)
                raise TimeoutError('Превышено время ожидания воспроизведения')
        current()
        return self.ticket.result(0)
