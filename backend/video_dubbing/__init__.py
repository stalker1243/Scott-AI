"""Модуль озвучки видео."""
from .engine import (
    VideoDubber,
    DubbingConfig,
    CharacterVoice,
    DialogueLine,
    get_default_dubber
)

__all__ = [
    "VideoDubber",
    "DubbingConfig",
    "CharacterVoice",
    "DialogueLine",
    "get_default_dubber"
]

