"""
Ожидание ответа ИИ: ограничение по времени и повтор при лимите.

Замеры на живой машине: средний ответ 7.3 секунды, а худшие пять процентов —
29 секунд. Запрос уходил вообще без ограничения по времени, и библиотека ждала
столько, сколько потребуется. Рядом в логе — «429 Too Many Requests»: у
бесплатного тарифа Groq есть предел, и при его достижении Scott просто
замолкал, хотя достаточно подождать секунду.

Сеть здесь не трогается: вызов модели подменяется.
"""

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def answerer(monkeypatch):
    try:
        import intelligent_answerer as module
    except ImportError:
        from backend import intelligent_answerer as module

    monkeypatch.setattr(module.IntelligentAnswerer, "__init__", lambda self: None)

    # Пауза между попытками не должна замедлять проверки.
    monkeypatch.setattr(module.time, "sleep", lambda _: None)

    instance = module.IntelligentAnswerer()
    instance.module = module
    return instance


def test_rate_limit_is_retried(answerer):
    """
    Отказ по лимиту — повод подождать и повторить, а не молчать.

    Именно он стоял в логе живого разговора пять раз подряд.
    """
    attempts = []

    def call():
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("Error code: 429 - Too Many Requests")
        return "готово"

    assert answerer._ask_with_retry(call, "Groq") == "готово"
    assert len(attempts) == 2, "повтора не было"


def test_timeout_is_retried(answerer):
    """Обрыв связи тоже стоит повторить: сеть моргает чаще, чем ломается."""
    attempts = []

    def call():
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("Request timed out")
        return "готово"

    assert answerer._ask_with_retry(call, "Groq") == "готово"
    assert len(attempts) == 2


def test_bad_key_is_not_retried(answerer):
    """
    Пара к тестам выше: неверный ключ со второй попытки не исправится.

    Повторять такое — значит вдвое дольше держать человека в ожидании ответа,
    которого не будет.
    """
    attempts = []

    def call():
        attempts.append(1)
        raise RuntimeError("Error code: 401 - Invalid API Key")

    with pytest.raises(RuntimeError):
        answerer._ask_with_retry(call, "Groq")

    assert len(attempts) == 1, "неверный ключ пробовали повторно"


def test_gives_up_after_limit(answerer):
    """
    Бесконечно пробовать нельзя: человек ждёт ответа, а не упорства.
    """
    attempts = []

    def call():
        attempts.append(1)
        raise RuntimeError("429 rate limit")

    with pytest.raises(RuntimeError):
        answerer._ask_with_retry(call, "Groq")

    assert len(attempts) == answerer.module.MAX_ATTEMPTS


def test_service_pause_respected(answerer, monkeypatch):
    """
    Если сервис сам назвал паузу, ждём столько, сколько он просит.

    Но не дольше собственного таймаута запроса: иначе повтор обошёлся бы
    дороже, чем отказ.
    """
    slept = []
    monkeypatch.setattr(answerer.module.time, "sleep", lambda s: slept.append(s))

    attempts = []

    def call():
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("429 too many requests, retry-after: 3.5")
        return "готово"

    answerer._ask_with_retry(call, "Groq")

    assert slept == [3.5]


def test_absurd_pause_capped(answerer, monkeypatch):
    """Пауза длиннее таймаута обрезается — ждать дольше бессмысленно."""
    slept = []
    monkeypatch.setattr(answerer.module.time, "sleep", lambda s: slept.append(s))

    attempts = []

    def call():
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("429 too many requests, retry-after: 600")
        return "готово"

    answerer._ask_with_retry(call, "Groq")

    assert slept == [answerer.module.REQUEST_TIMEOUT_SECONDS]


def test_timeout_is_set_and_sane():
    """
    Ограничение по времени должно существовать и быть разумным.

    Без него библиотека ждёт минутами — с этого всё и началось.
    """
    try:
        import intelligent_answerer as module
    except ImportError:
        from backend import intelligent_answerer as module

    assert 5 <= module.REQUEST_TIMEOUT_SECONDS <= 60
    assert module.MAX_ATTEMPTS >= 2
