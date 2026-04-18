"""
Постоянная память диалога для Мальтруанта.

Идея:
- история диалога хранится в jsonl (по одной записи на строку)
- при старте можно подгружать последние N реплик

Это простая реализация, безопасная и прозрачная:
никаких бинарников, только текст.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional
import json


@dataclass
class MemoryConfig:
    path: Path
    max_lines: int = 2000  # ограничение файла, чтобы не разрастался бесконечно


class MemoryStore:
    def __init__(self, config: MemoryConfig):
        self.config = config
        self.config.path.parent.mkdir(parents=True, exist_ok=True)

    def append_turn(self, question: str, answer: str) -> None:
        record = {"q": question, "a": answer}
        with self.config.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._trim_if_needed()

    def load_last_turns(self, limit: int = 50) -> List[Tuple[str, str]]:
        if not self.config.path.exists():
            return []
        try:
            lines = self.config.path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            return []

        turns: List[Tuple[str, str]] = []
        for line in lines[-limit:]:
            try:
                obj = json.loads(line)
                q = str(obj.get("q", "")).strip()
                a = str(obj.get("a", "")).strip()
                if q or a:
                    turns.append((q, a))
            except Exception:
                continue
        return turns

    def _trim_if_needed(self) -> None:
        # Если файл слишком большой, оставляем только последние max_lines строк
        if not self.config.path.exists():
            return
        try:
            lines = self.config.path.read_text(encoding="utf-8", errors="ignore").splitlines()
            if len(lines) <= self.config.max_lines:
                return
            lines = lines[-self.config.max_lines :]
            self.config.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception:
            # Если что-то пошло не так — просто не трогаем файл
            return


