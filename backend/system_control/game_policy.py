"""Политики игровых сессий: offline/online."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import time


class GameMode(str, Enum):
    OFFLINE = "offline"
    ONLINE = "online"
    UNKNOWN = "unknown"


@dataclass
class GameSession:
    name: str
    mode: GameMode
    started_at: float


@dataclass
class PolicyDecision:
    allowed: bool = True
    message: str = ""
    should_stop: bool = False
    should_advise: bool = False


class GamePolicy:
    def __init__(self, offline_limit_minutes: int = 90) -> None:
        self.offline_limit_seconds = max(15, offline_limit_minutes) * 60

    def evaluate(self, session: GameSession) -> PolicyDecision:
        elapsed = max(0.0, time.time() - session.started_at)
        if session.mode is GameMode.OFFLINE and elapsed >= self.offline_limit_seconds:
            return PolicyDecision(allowed=True, should_stop=True)
        if session.mode is GameMode.ONLINE and elapsed >= self.offline_limit_seconds:
            return PolicyDecision(allowed=True, should_advise=True)
        return PolicyDecision(allowed=True)

    def pre_start_message(self, session: GameSession) -> str:
        if session.mode is GameMode.ONLINE:
            return "Перед онлайн-игрой рекомендую заранее определить длительность сессии."
        if session.mode is GameMode.OFFLINE:
            return "Офлайн-режим запущен. При долгой сессии я автоматически предложу сделать паузу."
        return "Запускаю игру. Для точного контроля скажи: офлайн или онлайн."

    def can_stop_by_command(self, session: GameSession) -> PolicyDecision:
        if session.mode is GameMode.ONLINE:
            return PolicyDecision(
                allowed=False,
                message="Онлайн-игру после старта я не останавливаю автоматически. Сначала выйди из матча.",
            )
        return PolicyDecision(allowed=True)
