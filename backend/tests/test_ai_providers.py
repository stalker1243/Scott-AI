"""
Провайдеры моделей: Claude, шлюз к сотням моделей и остальные.

Проверяется то, на чём такие вещи ломаются, и то, что уже ломалось однажды.

Ломалось: захардкоженная модель Groq оказалась снята с поддержки, и Scott
переставал отвечать на ровном месте. Отсюда правило — список моделей
спрашивается у провайдера живым запросом, а статический каталог остаётся
только на случай, когда ключа ещё нет: выбрать модель человек должен ДО того,
как ключ применён.

Ломается обычно на различиях в формате. У Anthropic системная подсказка идёт
отдельным полем, а не первым сообщением в списке: роль "system" в списке он не
принимает и отвечает отказом на весь запрос. Это и проверяется — не текстом
ответа, а тем, что именно ушло в запрос.

Сеть здесь не трогается ни разу: запросы перехватываются.
"""

import json

import pytest

pytestmark = pytest.mark.unit


try:
    import intelligent_answerer as ia
except ImportError:  # pragma: no cover — запуск из корня репозитория
    from backend import intelligent_answerer as ia


class Ответ:
    """Подделка ответа сети."""

    def __init__(self, payload, code=200):
        self._payload = payload
        self.status_code = code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


@pytest.fixture
def отвечающий():
    """Отвечающий без единого ключа: подключаться он никуда не станет."""
    помощник = ia.IntelligentAnswerer.__new__(ia.IntelligentAnswerer)
    помощник.custom_keys = {}
    помощник.env_keys = {}
    помощник.model = ""
    помощник.temperature = 0.7
    помощник.max_tokens = 1000
    помощник.client = None
    помощник.api_provider = None
    помощник.enabled = False
    помощник.last_connect_error = ""
    помощник.memory = ia.ConversationMemory(max_history=6)
    помощник.system_prompt = "Ты Scott AI."
    return помощник


# ==================== Каталог ====================

def test_claude_and_gateway_are_offered():
    """Claude и шлюз к сотням моделей должны быть в списке провайдеров."""
    assert "Anthropic" in ia.STATIC_PROVIDER_MODELS
    assert "OpenRouter" in ia.STATIC_PROVIDER_MODELS


def test_every_provider_offers_at_least_one_model():
    """
    У провайдера без моделей выбрать нечего, а без модели не применить ключ.

    Это и есть смысл статического каталога: он нужен ровно до того момента,
    когда ключ введён и можно спросить живой список.
    """
    for провайдер, модели in ia.STATIC_PROVIDER_MODELS.items():
        assert модели, f"{провайдер}: пустой каталог"
        for модель in модели:
            assert модель.get("id"), f"{провайдер}: модель без названия"


def test_model_names_look_like_model_names():
    """
    Название модели — то, что уйдёт в запрос дословно.

    Опечатка здесь не видна нигде до первого вопроса, а потом каждый ответ
    падает с «модель недоступна».
    """
    for провайдер, модели in ia.STATIC_PROVIDER_MODELS.items():
        for модель in модели:
            ident = модель["id"]
            assert ident == ident.strip(), f"{провайдер}: пробелы в «{ident}»"
            assert " " not in ident, f"{провайдер}: пробел внутри «{ident}»"
            assert ident.lower() == ident, f"{провайдер}: заглавные в «{ident}»"


# ==================== Живые списки ====================

def test_live_list_wins_over_static(отвечающий, monkeypatch):
    """
    Живой список заменяет статический, когда его удалось получить.

    Ровно та защита, которой не хватало Groq: провайдер сам знает, что у него
    сейчас есть, а записанное в коде устаревает молча.
    """
    отвечающий.env_keys = {"Anthropic": "ключ"}

    monkeypatch.setattr(ia, "list_anthropic_models",
                        lambda key: [{"id": "claude-из-живого-списка", "note": ""}])
    monkeypatch.setattr(ia, "list_openrouter_models", lambda key: [])
    monkeypatch.setattr(ia, "list_groq_models", lambda key: [])

    провайдеры = {p["id"]: p for p in отвечающий.get_available_providers()}
    имена = [m["id"] for m in провайдеры["Anthropic"]["models"]]

    assert имена == ["claude-из-живого-списка"]


def test_static_list_is_used_when_live_one_fails(отвечающий, monkeypatch):
    """
    Не ответил провайдер — показываем запасной каталог.

    Сеть могла не подняться, ключ мог устареть. Пустой список означал бы, что
    выбрать нельзя ничего, и человек застрял бы на ровном месте.
    """
    отвечающий.env_keys = {"Anthropic": "ключ"}

    monkeypatch.setattr(ia, "list_anthropic_models", lambda key: [])
    monkeypatch.setattr(ia, "list_openrouter_models", lambda key: [])
    monkeypatch.setattr(ia, "list_groq_models", lambda key: [])

    провайдеры = {p["id"]: p for p in отвечающий.get_available_providers()}

    assert провайдеры["Anthropic"]["models"] == ia.STATIC_PROVIDER_MODELS["Anthropic"]


def test_gateway_catalogue_is_shown_without_a_key(отвечающий, monkeypatch):
    """
    Каталог шлюза виден и без ключа.

    У него он открытый, и это тот редкий случай, когда человек может выбрать
    модель до того, как что-либо вводил.
    """
    спрошено = {}

    def список(key=""):
        спрошено["ключ"] = key
        return [{"id": "поставщик/модель", "note": "", "free": True}]

    monkeypatch.setattr(ia, "list_openrouter_models", список)
    monkeypatch.setattr(ia, "list_anthropic_models", lambda key: [])
    monkeypatch.setattr(ia, "list_groq_models", lambda key: [])

    провайдеры = {p["id"]: p for p in отвечающий.get_available_providers()}

    assert спрошено.get("ключ") == ""
    assert провайдеры["OpenRouter"]["models"][0]["id"] == "поставщик/модель"
    assert провайдеры["OpenRouter"]["configured"] is False


def test_free_gateway_models_come_first(monkeypatch):
    """
    Бесплатные модели шлюза — наверху списка.

    В каталоге на сотни строк их иначе не найти, а начинать знакомство разумно
    именно с них.
    """
    monkeypatch.setattr(ia.requests, "get", lambda *a, **k: Ответ({"data": [
        {"id": "дорогая/модель", "name": "Дорогая", "pricing": {"prompt": "0.00001"}},
        {"id": "бесплатная/модель", "name": "Бесплатная", "pricing": {"prompt": "0"}},
    ]}))

    модели = ia.list_openrouter_models("ключ")

    assert модели[0]["id"] == "бесплатная/модель"


def test_gateway_offers_only_talking_models(monkeypatch):
    """
    Из каталога шлюза берутся только разговорные модели.

    Там же лежат рисование, музыка и распознавание речи. В списке выбора они
    были бы обещанием, которое некому выполнить: Scott умеет только
    разговаривать текстом.
    """
    monkeypatch.setattr(ia.requests, "get", lambda *a, **k: Ответ({"data": [
        {"id": "кто-то/музыка", "architecture": {"modality": "text->audio"},
         "pricing": {"prompt": "0"}},
        {"id": "кто-то/рисование", "architecture": {"modality": "text->image"},
         "pricing": {"prompt": "0"}},
        {"id": "кто-то/разговор", "architecture": {"modality": "text->text"},
         "pricing": {"prompt": "0.001"}},
        {"id": "кто-то/зрение", "architecture": {"modality": "text+image->text"},
         "pricing": {"prompt": "0.001"}},
    ]}))

    имена = [m["id"] for m in ia.list_openrouter_models("ключ")]

    assert "кто-то/разговор" in имена
    # Модель, которая умеет ещё и смотреть картинки, отвечает текстом и годится.
    assert "кто-то/зрение" in имена
    assert "кто-то/музыка" not in имена
    assert "кто-то/рисование" not in имена


def test_network_failure_does_not_raise(monkeypatch):
    """
    Провайдер недоступен — список пуст, но никто не падает.

    Список моделей запрашивается при открытии Настроек; уронить из-за него всю
    страницу было бы несоразмерно.
    """
    def взрыв(*a, **k):
        raise ConnectionError("сети нет")

    monkeypatch.setattr(ia.requests, "get", взрыв)

    assert ia.list_anthropic_models("ключ") == []
    assert ia.list_openrouter_models("ключ") == []


# ==================== Формат запроса ====================

def test_claude_gets_system_prompt_separately(отвечающий, monkeypatch):
    """
    Системная подсказка уходит Claude отдельным полем, а не сообщением.

    Роль "system" в списке сообщений Anthropic не принимает и отвечает отказом
    на весь запрос. Проверяется именно отправленное, а не полученное: ошибка
    такого рода видна только в теле запроса.
    """
    отправлено = {}

    def запрос(url, headers=None, json=None, timeout=None):
        отправлено["url"] = url
        отправлено["headers"] = headers
        отправлено["body"] = json
        return Ответ({"content": [{"type": "text", "text": "Ответ Claude."}]})

    monkeypatch.setattr(ia.requests, "post", запрос)

    отвечающий.api_provider = "Anthropic"
    отвечающий.client = {"api_key": "ключ", "base_url": ia.ANTHROPIC_BASE}
    отвечающий.model = "claude-sonnet-5"
    отвечающий.enabled = True

    ответ, успех = отвечающий.answer("что такое фотосинтез", use_memory=False)

    assert успех
    assert ответ == "Ответ Claude."

    body = отправлено["body"]
    assert body["system"] == отвечающий.system_prompt
    assert all(m["role"] != "system" for m in body["messages"]), \
        "роль system осталась в списке сообщений — Anthropic такой запрос отвергнет"

    # Ключ и версия идут в собственных заголовках, а не в Authorization.
    assert отправлено["headers"]["x-api-key"] == "ключ"
    assert отправлено["headers"]["anthropic-version"] == ia.ANTHROPIC_VERSION


def test_claude_answer_is_glued_from_pieces(отвечающий, monkeypatch):
    """
    Ответ Claude приходит кусками, и склеить их нужно самому.

    Взять только первый кусок — значит потерять хвост ответа на длинных
    объяснениях, где куски и появляются.
    """
    monkeypatch.setattr(ia.requests, "post", lambda *a, **k: Ответ({"content": [
        {"type": "text", "text": "Первая часть. "},
        {"type": "text", "text": "Вторая часть."},
    ]}))

    отвечающий.api_provider = "Anthropic"
    отвечающий.client = {"api_key": "ключ", "base_url": ia.ANTHROPIC_BASE}
    отвечающий.model = "claude-sonnet-5"
    отвечающий.enabled = True

    ответ, успех = отвечающий.answer("вопрос", use_memory=False)

    assert успех
    assert ответ == "Первая часть. Вторая часть."


def test_gateway_speaks_openai_format(отвечающий, monkeypatch):
    """Шлюз совместим с OpenAI: системная подсказка остаётся в сообщениях."""
    отправлено = {}

    def запрос(url, headers=None, json=None, timeout=None):
        отправлено["url"] = url
        отправлено["body"] = json
        return Ответ({"choices": [{"message": {"content": "Ответ шлюза."}}]})

    monkeypatch.setattr(ia.requests, "post", запрос)

    отвечающий.api_provider = "OpenRouter"
    отвечающий.client = {"api_key": "ключ", "base_url": ia.OPENROUTER_BASE}
    отвечающий.model = "anthropic/claude-sonnet-5"
    отвечающий.enabled = True

    ответ, успех = отвечающий.answer("вопрос", use_memory=False)

    assert успех
    assert ответ == "Ответ шлюза."
    assert отправлено["body"]["messages"][0]["role"] == "system"
    assert отправлено["url"].startswith(ia.OPENROUTER_BASE)


def test_brief_request_reaches_claude(отвечающий, monkeypatch):
    """
    Признак «спросили голосом» доходит и до Claude.

    Через этот признак задаётся короткая подсказка и меньший предел длины —
    иначе вслух зачитывается ответ на полтысячи знаков со списками. Один раз он
    уже терялся по дороге, и терялся молча.
    """
    отправлено = {}

    def запрос(url, headers=None, json=None, timeout=None):
        отправлено["body"] = json
        return Ответ({"content": [{"type": "text", "text": "Коротко."}]})

    monkeypatch.setattr(ia.requests, "post", запрос)

    отвечающий.api_provider = "Anthropic"
    отвечающий.client = {"api_key": "ключ", "base_url": ia.ANTHROPIC_BASE}
    отвечающий.model = "claude-sonnet-5"
    отвечающий.enabled = True

    отвечающий.answer("вопрос", use_memory=False, brief=True)

    assert отправлено["body"]["system"] == ia.BRIEF_SYSTEM_PROMPT
    assert отправлено["body"]["max_tokens"] == ia.BRIEF_MAX_TOKENS
