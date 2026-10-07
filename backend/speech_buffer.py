"""Collect verified speech blocks before playback without changing their PCM."""
import math
import wave

BUFFER_MODES = {
    'immediate': ('Сразу', 0),
    '2s': ('2 секунды звука', 2),
    '4s': ('4 секунды звука', 4),
    'complete': ('Вся фраза', None),
}
MAX_BLOCKS = 128


class SpeechBuffer:
    def __init__(self, mode='immediate'):
        if not isinstance(mode, str) or mode not in BUFFER_MODES:
            raise ValueError('Unknown speech buffer mode')
        self.target = BUFFER_MODES[mode][1]
        self._pending = []
        self._seconds = 0.
        self._released = False
        self._finished = False

    def push(self, audio, last):
        if self._finished or not isinstance(last, bool):
            raise ValueError('Invalid speech buffer sequence')
        if self.target != 0 and not self._released:
            seconds = audio.seconds
            if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds <= 0:
                raise ValueError('Invalid speech block duration')
            self._seconds += seconds
        self._pending.append(audio)
        if len(self._pending) > MAX_BLOCKS:
            raise ValueError('Excessive speech buffer')
        self._finished = last
        if last or self._released or (self.target is not None and self._seconds >= self.target):
            result, self._pending = self._pending, []
            self._released = True
            return result
        return []

    def discard(self):
        self._pending.clear()
        self._finished = True


def join_wavs(paths, destination):
    """Copy PCM16/mono/24k blocks into one caller-owned temporary WAV."""
    if not 1 <= len(paths) <= MAX_BLOCKS:
        raise ValueError('Invalid speech block count')
    with wave.open(str(destination), 'wb') as output:
        output.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        for path in paths:
            with wave.open(str(path), 'rb') as source:
                frames = source.getnframes()
                if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 24000) or not 0 < frames <= 120000:
                    raise ValueError('Invalid speech block format')
                data = source.readframes(frames)
                if len(data) != frames * 2:
                    raise ValueError('Truncated speech block')
                output.writeframesraw(data)
    return str(destination)
