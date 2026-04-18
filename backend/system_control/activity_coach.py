"""Коуч активности: анти-спам советов."""
from __future__ import annotations

import time


class ActivityCoach:
    def __init__(self, advice_cooldown_minutes: int = 20, offline_game_limit_minutes: int = 90) -> None:
        self.cooldown_seconds = max(5, advice_cooldown_minutes) * 60
        self.offline_limit_seconds = max(15, offline_game_limit_minutes) * 60
        self.last_spoken_at: float = 0.0
        self.last_online_warning_at: float = 0.0

    def can_speak(self) -> bool:
        return (time.time() - self.last_spoken_at) >= self.cooldown_seconds

    def mark_spoken(self) -> None:
        self.last_spoken_at = time.time()

    def mark_online_start_warning(self) -> None:
        self.last_online_warning_at = time.time()
