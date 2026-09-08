"""
Настройка ИИ переживает неудачный старт.

Живая жалоба: после каждого запуска приходилось вводить ключ заново. Ключ при
этом никуда не девался — он лежал в data/ai_config.json, — но подключение
проверялось ровно один раз, при старте backend. А стартует он вместе с
загрузкой Whisper и Silero, часто сразу после включения компьютера, когда сеть
ещё не поднялась. Одной неудачи хватало, чтобы ИИ молчал до перезапуска.
"""

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def answerer(monkeypatch):
    """Ответчик без единого похода в сеть."""
    try:
        import intelligent_answerer as module
    except ImportError:
        from backend import intelligent_answerer as module

    monkeypatch.setattr(module.IntelligentAnswerer, "__init__", lambda self: None)

    instance = module.IntelligentAnswerer()
    instance.enabled = False
    instance.client = None
    instance.api_provider = None
    instance.model = None
    instance.custom_keys = {"Groq": "тестовый-ключ"}
    instance.env_keys = {"Groq": None, "OpenAI": None, "DeepSeek": None}
    instance.pending_config = {"provider": "Groq", "model": "llama-3.3-70b-versatile"}
    instance.last_connect_error = ""
    return instance


def test_retry_reconnects_later(answerer, monkeypatch):
    """
    Вторая попытка делается при первом же обращении.

    К этому времени сеть обычно уже есть, и человеку не приходится вводить
    ключ заново.
    """
    attempts = []

    def connect(provider, model, key):
        attempts.append((provider, model))
        answerer.enabled = True
        return True

    monkeypatch.setattr(answerer, "_connect_provider", connect)

    assert answerer.retry_pending_connection() is True
    assert attempts == [("Groq", "llama-3.3-70b-versatile")]
    assert answerer.pending_config is None, "повторять больше незачем"


def test_retry_keeps_config_after_failure(answerer, monkeypatch):
    """
    Если и вторая попытка не удалась, настройка всё равно не выбрасывается.

    Сеть могла не появиться и к этому моменту — но ключ по-прежнему верный.
    """
    monkeypatch.setattr(answerer, "_connect_provider", lambda *a: False)

    assert answerer.retry_pending_connection() is False
    assert answerer.pending_config is not None


def test_no_retry_when_already_connected(answerer, monkeypatch):
    """Пара к тестам выше: работающее подключение не трогаем."""
    answerer.enabled = True
    monkeypatch.setattr(
        answerer, "_connect_provider",
        lambda *a: pytest.fail("переподключались при работающем ИИ"),
    )

    assert answerer.retry_pending_connection() is False
