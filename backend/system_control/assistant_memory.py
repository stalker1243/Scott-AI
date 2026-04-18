"""Простая долговременная память ассистента."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List
import json


@dataclass
class AssistantProfile:
    goals: List[str]
    preferred_topics: List[str]
    last_focus_topic: str


class AssistantMemory:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.profile = self._load()

    def _load(self) -> AssistantProfile:
        if not self.path.exists():
            return AssistantProfile(goals=[], preferred_topics=[], last_focus_topic="")
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return AssistantProfile(
                goals=list(data.get("goals", [])),
                preferred_topics=list(data.get("preferred_topics", [])),
                last_focus_topic=str(data.get("last_focus_topic", "")),
            )
        except Exception:
            return AssistantProfile(goals=[], preferred_topics=[], last_focus_topic="")

    def save(self) -> None:
        self.path.write_text(json.dumps(asdict(self.profile), ensure_ascii=False, indent=2), encoding="utf-8")

    def remember_goal(self, goal: str) -> None:
        g = goal.strip()
        if not g:
            return
        if g not in self.profile.goals:
            self.profile.goals.append(g)
            self.save()

    def remember_topic(self, topic: str) -> None:
        t = topic.strip().lower()
        if not t:
            return
        self.profile.last_focus_topic = t
        if t not in self.profile.preferred_topics:
            self.profile.preferred_topics.append(t)
        self.save()
