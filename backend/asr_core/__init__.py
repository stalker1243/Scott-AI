"""Модуль распознавания речи (ASR - Automatic Speech Recognition)."""
from .engine import AsrEngine, AsrConfig, get_default_asr_engine

__all__ = ["AsrEngine", "AsrConfig", "get_default_asr_engine"]

