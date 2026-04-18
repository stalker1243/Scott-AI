"""Лёгкое воспроизведение WAV без внешнего плеера."""
from __future__ import annotations

import os
import threading
from pathlib import Path


def play_audio(path: Path) -> bool:
    """
    Пытается воспроизвести файл без запуска внешнего UI-плеера.
    Возвращает True при успешном запуске воспроизведения.
    """
    audio_path = Path(path)
    if not audio_path.exists():
        return False

    # Сначала пробуем sounddevice/soundfile: обычно надёжнее на кастомных аудио-устройствах.
    try:
        import sounddevice as sd  # type: ignore
        import soundfile as sf  # type: ignore

        audio, sr = sf.read(str(audio_path), dtype="float32", always_2d=False)
        sd.play(audio, sr, blocking=False)
        return True
    except Exception:
        pass

    # На Windows используем встроенный winsound (без открытия плеера).
    try:
        import winsound  # type: ignore

        winsound.PlaySound(
            str(audio_path),
            winsound.SND_FILENAME | winsound.SND_ASYNC | getattr(winsound, "SND_NODEFAULT", 0),
        )
        return True
    except Exception:
        pass

    # Последний фолбэк: os.startfile в отдельном потоке, чтобы не подвисать.
    try:
        if hasattr(os, "startfile"):
            threading.Thread(
                target=lambda: os.startfile(str(audio_path)),  # type: ignore[attr-defined]
                daemon=True,
            ).start()
            return True
    except Exception:
        return False
    return False
