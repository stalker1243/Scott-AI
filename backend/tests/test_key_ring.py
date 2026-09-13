"""
Связка ключей: запасные подхватываются сами.

Бесплатные модели шлюза ограничены числом запросов, и один ключ упирается в
предел быстро. Несколько ключей снимают эту беду — но только если Scott
переходит с одного на другой сам: иначе человеку придётся править настройки и
перезапускать backend посреди работы, хотя он всего лишь задал вопрос.

Проверяется именно переход, а не хранение: связка без перебора превращает
второй и третий ключи в мёртвый груз.
"""

import pytest

pytestmark = pytest.mark.unit


try:
    import key_ring
except ImportError:  # pragma: no cover — запуск из корня репозитория
    from backend import key_ring


# ==================== Что попадает в связку ====================

def test_empty_slots_are_ignored():
    """
    Незаполненные переменные не считаются ключами.

    В .env заготовлено три строки, а заполнена может быть одна: остальные
    останутся пустыми, и принимать их за ключи нельзя.
    """
    ring = key_ring.KeyRing(["ключ", "", "   ", None])

    assert len(ring) == 1
    assert ring.current() == "ключ"


def test_duplicates_are_dropped():
    """Один ключ, вставленный дважды, не даёт двух попыток."""
    ring = key_ring.KeyRing(["один", "один", "два"])

    assert ring.all == ["один", "два"]


def test_order_is_kept():
    """Первый ключ основной, остальные запасные: пока первый жив, он и в деле."""
    ring = key_ring.KeyRing(["первый", "второй", "третий"])

    assert ring.current() == "первый"
    assert ring.current() == "первый"


def test_empty_ring_gives_nothing():
    ring = key_ring.KeyRing(["", ""])

    assert len(ring) == 0
    assert ring.current() is None


# ==================== Переход на запасной ====================

def test_rate_limited_key_is_set_aside():
    """Ключ, упёршийся в предел, уступает место следующему."""
    ring = key_ring.KeyRing(["первый", "второй"])

    assert ring.set_aside("первый", "rate") is True
    assert ring.current() == "второй"


def test_last_key_says_there_is_no_spare():
    """
    Когда запасных не осталось, связка так и говорит.

    По этому признаку решается, повторять запрос или сдаться: повторять с тем
    же ключом бессмысленно.
    """
    ring = key_ring.KeyRing(["единственный"])

    assert ring.set_aside("единственный", "rate") is False


def test_bad_key_is_set_aside_for_longer():
    """
    Неверный ключ откладывается надолго, а упёршийся в предел — ненадолго.

    Пределы считаются по минутам, и через минуту ключ снова годен. Неверный
    же сам по себе верным не станет, и перебирать его каждую минуту — пустая
    трата запросов.
    """
    assert key_ring.BAD_KEY_PAUSE > key_ring.RATE_LIMIT_PAUSE * 10


def test_set_aside_key_returns_when_time_passes(monkeypatch):
    """
    Отложенный ключ возвращается в строй.

    Иначе после часа работы все три оказались бы отложены навсегда, и Scott
    замолчал бы, хотя пределы давно отпустили.
    """
    часы = [1000.0]
    monkeypatch.setattr(key_ring.time, "monotonic", lambda: часы[0])

    ring = key_ring.KeyRing(["первый", "второй"])
    ring.set_aside("первый", "rate")

    assert ring.current() == "второй"

    часы[0] += key_ring.RATE_LIMIT_PAUSE + 1

    assert ring.ready() == 2


def test_all_keys_aside_still_returns_something(monkeypatch):
    """
    Когда отложены все, связка отдаёт тот, чей срок истекает раньше.

    Отказ с понятной причиной полезнее, чем молчание о том, что ключей будто
    бы нет вовсе.
    """
    часы = [1000.0]
    monkeypatch.setattr(key_ring.time, "monotonic", lambda: часы[0])

    ring = key_ring.KeyRing(["первый", "второй"])
    ring.set_aside("первый", "rate")
    ring.set_aside("второй", "rate")

    assert ring.ready() == 0
    assert ring.current() in ("первый", "второй")


# ==================== Из-за чего отказали ====================

@pytest.mark.parametrize("причина", [
    "429 Client Error: Too Many Requests",
    "Rate limit exceeded for free models",
    "too many requests, slow down",
])
def test_rate_limit_is_recognised(причина):
    assert key_ring.why_refused(причина) == "rate"


@pytest.mark.parametrize("причина", [
    "401 Unauthorized",
    "Invalid API key provided",
    "No auth credentials found",
])
def test_bad_key_is_recognised(причина):
    assert key_ring.why_refused(причина) == "bad"


@pytest.mark.parametrize("причина", [
    "Your credit balance is too low",
    "model not found",
    "500 Internal Server Error",
    "",
])
def test_other_troubles_do_not_trigger_a_switch(причина):
    """
    Смена ключа помогает не от всякой беды.

    Кончившиеся деньги не появятся оттого, что мы попробуем другой ключ того
    же счёта, а недоступная модель не станет доступной. Перебирать связку
    впустую — значит тратить запросы и время человека.
    """
    assert key_ring.why_refused(причина) is None
