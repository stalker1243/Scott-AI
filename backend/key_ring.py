"""
Связка ключей одного провайдера.

Бесплатные модели ограничены числом запросов, и один ключ упирается в предел
быстро. Несколько ключей снимают эту беду — но только если Scott переходит с
одного на другой сам: иначе человеку придётся править настройки и
перезапускать backend посреди работы, хотя он всего лишь задал вопрос.

Ключ, упёршийся в предел, откладывается ненадолго: пределы считаются по
минутам, и через минуту он снова годен. Ключ, отвергнутый как неверный,
откладывается надолго — сам по себе он верным не станет, и перебирать его
каждую минуту бессмысленно.
"""

from __future__ import annotations

import time
from typing import List, Optional


# Через сколько ключ, упёршийся в предел запросов, снова годен.
RATE_LIMIT_PAUSE = 65

# Через сколько возвращается ключ, который отвергли. Долго: неверный ключ сам
# не исправится, но и вычёркивать его навсегда не стоит — человек мог
# перевыпустить его в личном кабинете.
BAD_KEY_PAUSE = 30 * 60


class KeyRing:
    """
    Несколько ключей одного провайдера с очередью.

    Порядок сохраняется: первый ключ — основной, остальные запасные. Пока
    основной работает, до запасных дело не доходит.
    """

    def __init__(self, keys: List[str]):
        # Пустые строки и повторы выбрасываются сразу: в .env легко оставить
        # незаполненную переменную или вставить один ключ дважды.
        self._keys: List[str] = []
        for key in keys:
            key = (key or "").strip()
            if key and key not in self._keys:
                self._keys.append(key)

        self._until: dict[str, float] = {}
        self._current = 0

    def __len__(self) -> int:
        return len(self._keys)

    @property
    def all(self) -> List[str]:
        return list(self._keys)

    def current(self) -> Optional[str]:
        """
        Ключ, которым работаем сейчас.

        Отложенные пропускаются. Если отложены все — возвращается тот, чей
        срок истекает раньше прочих: отказ с понятной причиной полезнее, чем
        молчание о том, что ключей будто бы нет вовсе.
        """
        if not self._keys:
            return None

        now = time.monotonic()

        for step in range(len(self._keys)):
            index = (self._current + step) % len(self._keys)
            key = self._keys[index]

            if self._until.get(key, 0) <= now:
                self._current = index
                return key

        return min(self._keys, key=lambda k: self._until.get(k, 0))

    def set_aside(self, key: str, reason: str) -> bool:
        """
        Отложить ключ и перейти к следующему.

        Возвращает True, если есть на что переходить: по этому признаку
        решается, повторять ли запрос.
        """
        if key not in self._keys:
            return False

        пауза = BAD_KEY_PAUSE if reason == "bad" else RATE_LIMIT_PAUSE
        self._until[key] = time.monotonic() + пауза

        now = time.monotonic()
        живые = [k for k in self._keys if self._until.get(k, 0) <= now]

        if not живые:
            return False

        self._current = self._keys.index(живые[0])
        return True

    def ready(self) -> int:
        """Сколько ключей готовы к работе прямо сейчас."""
        now = time.monotonic()
        return sum(1 for k in self._keys if self._until.get(k, 0) <= now)


def why_refused(reason: str) -> Optional[str]:
    """
    Из-за чего отказали: предел запросов, негодный ключ или что-то ещё.

    Различать важно: при пределе достаточно взять другой ключ, при негодном —
    тоже, но откладывать его надо надолго. Всё остальное менять ключ не
    поможет, и перебирать связку впустую незачем: кончившиеся деньги не
    появятся оттого, что мы попробуем другой ключ того же счёта.
    """
    text = (reason or "").lower()

    if "rate limit" in text or "429" in text or "too many requests" in text:
        return "rate"

    if any(marker in text for marker in (
            "invalid api key", "invalid_api_key", "unauthorized", "401",
            "no auth credentials", "user not found")):
        return "bad"

    return None
