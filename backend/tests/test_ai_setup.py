"""
Подключение ключа ИИ — то, с чем человек сталкивается первым делом.

Первый пользователь упёрся здесь в два тупика подряд, и оба видны только на
машине, где ИИ ещё не настроен:

  1. «У этого провайдера не нашлось моделей» — список моделей Groq
     запрашивался у самого Groq, а для этого нужен ключ. Замкнутый круг:
     без ключа нет моделей, без модели не применить ключ.
  2. «Не удалось подключиться … с этим ключом» — настоящая причина уходила в
     консоль, которой никто не видит.

Сеть здесь не трогается.
"""

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def answerer_module():
    try:
        import intelligent_answerer
    except ImportError:
        from backend import intelligent_answerer

    return intelligent_answerer


# ==================== Модели без ключа ====================

def test_groq_models_offered_without_key(answerer_module, monkeypatch):
    """
    Модели Groq видны ещё до ввода ключа.

    Иначе выбрать нечего, а без выбранной модели ключ не применить — человек
    заперт в круге.
    """
    module = answerer_module
    answerer = module.IntelligentAnswerer.__new__(module.IntelligentAnswerer)
    answerer.custom_keys = {}
    answerer.env_keys = {"Groq": "", "OpenAI": "", "DeepSeek": ""}

    providers = module.IntelligentAnswerer.get_available_providers(answerer)
    groq = next(p for p in providers if p["id"] == "Groq")

    assert groq["models"], "без ключа список моделей Groq пуст — выбрать нечего"


def test_fallback_models_have_ids(answerer_module):
    """У каждой запасной модели есть идентификатор и пояснение."""
    for model in answerer_module.GROQ_FALLBACK_MODELS:
        assert model["id"].strip()
        assert model["note"].strip()


# ==================== Объяснение отказов ====================

@pytest.mark.parametrize("reason,expected", [
    ('Error code: 401 - {"error":{"code":"invalid_api_key"}}', "не принял ключ"),
    ("Connection error.", "VPN"),
    ("Error code: 404 - model `x` does not exist", "недоступна"),
    ("Error code: 429 - rate limit exceeded", "ограничил"),
])
def test_reason_explained_in_human_words(answerer_module, reason, expected):
    """
    Человеку нужно знать, что делать дальше: перепроверить ключ, включить VPN
    или выбрать другую модель. «Connection error» из библиотеки на этот вопрос
    не отвечает.
    """
    text = answerer_module.explain_connect_error("Groq", "some-model", reason)
    assert expected.lower() in text.lower(), f"причина «{reason}» объяснена как: {text}"


def test_unknown_reason_still_reported(answerer_module):
    """Даже непонятную причину показываем, а не прячем за общей фразой."""
    text = answerer_module.explain_connect_error("Groq", "m", "Что-то странное")
    assert "Что-то странное" in text


def test_bad_key_recognised(answerer_module):
    """
    Отказ по ключу отличается от отказа по модели: в первом случае подбирать
    другую модель бессмысленно, ключ всё равно не примут.
    """
    assert answerer_module._looks_like_bad_key("Error code: 401 Invalid API Key")
    assert not answerer_module._looks_like_bad_key("model does not exist")
