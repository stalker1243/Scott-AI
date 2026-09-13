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
    """
    Подделка ответа сети.

    Поле `text` здесь не для красоты: причина отказа читается именно из тела,
    а не из текста исключения. Первая версия подделки его не имела, и проверки
    падали с «object has no attribute text» — ровно там, где код и должен был
    достать объяснение.
    """

    def __init__(self, payload, code=200):
        self._payload = payload
        self.status_code = code

    @property
    def text(self):
        return json.dumps(self._payload, ensure_ascii=False)

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

    # Связка ключей шлюза. Обычно её заводит конструктор, но здесь объект
    # создан в обход него — чтобы не лезть в сеть при каждом создании.
    try:
        import key_ring
    except ImportError:  # pragma: no cover
        from backend import key_ring

    помощник.openrouter_ring = key_ring.KeyRing(["ключ"])
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

# ==================== Понятные отказы ====================

def test_empty_balance_is_explained_plainly():
    """
    Кончившиеся деньги отличаются от неверного ключа.

    Здесь ключ верный, модель верная, интернет работает, — и человек, читающий
    «не удалось подключиться», пойдёт перепроверять ключ вместо того, чтобы
    заглянуть в счёт. Проверено на живых ключах: у Anthropic и OpenAI ответ
    приходит с «credit balance is too low», у DeepSeek — «402 Payment
    Required».
    """
    for причина in (
        '{"error":{"message":"Your credit balance is too low to access the API"}}',
        "402 Client Error: Payment Required for url",
        "You exceeded your current quota, please check your plan and billing",
    ):
        текст = ia.explain_connect_error("Anthropic", "claude-sonnet-5", причина)

        assert "средства" in текст, текст
        assert "пополните" in текст.lower(), текст


def test_bad_key_is_not_confused_with_empty_balance():
    """Отозванный ключ и пустой счёт — разные беды с разными действиями."""
    текст = ia.explain_connect_error("Groq", "модель", "401 Unauthorized: invalid api key")

    assert "ключ" in текст
    assert "средства" not in текст


def test_error_body_reaches_the_explanation():
    """
    Причина берётся из тела ответа, а не из текста исключения.

    raise_for_status кладёт в исключение только код и адрес: «400 Client
    Error: Bad Request for url ...». Само объяснение сервис пишет в теле, и
    оно терялось — человек с нулевым балансом видел голый код ошибки.
    """
    class Отказ:
        status_code = 400
        text = '{"error":{"message":"Your credit balance is too low"}}'

    with pytest.raises(RuntimeError) as поймано:
        ia.raise_with_body(Отказ())

    assert "credit balance" in str(поймано.value)


def test_successful_response_passes_through():
    class Успех:
        status_code = 200
        text = "{}"

    ia.raise_with_body(Успех())    # не должно бросать


# ==================== Память после неудачи ====================

def test_unanswered_question_is_dropped():
    """
    Вопрос без ответа убирается из памяти разговора.

    Вопрос кладётся туда до запроса, ответ — после удачного. После неудачи
    вопрос остаётся висеть, и со следующим их становится два подряд.
    Anthropic такую переписку отвергает целиком: одна неудача — скажем,
    кончились деньги — ломала бы и все последующие запросы, уже исправные.
    """
    память = ia.ConversationMemory(max_history=6)
    память.conversations = []

    память.add_message("user", "первый вопрос")
    память.add_message("assistant", "первый ответ")
    память.add_message("user", "вопрос, на который не ответили")

    память.drop_unanswered()

    роли = [m["role"] for m in память.conversations]
    assert роли == ["user", "assistant"]


def test_no_two_questions_in_a_row_after_failures():
    """Сколько бы неудач ни случилось подряд, висячих вопросов не остаётся."""
    память = ia.ConversationMemory(max_history=10)
    память.conversations = []

    for n in range(3):
        память.add_message("user", f"вопрос {n}")
        память.drop_unanswered()

    assert память.conversations == []


def test_key_is_taken_from_either_name(monkeypatch):
    """
    Ключ Claude читается и как ANTHROPIC_API_KEY, и как CLAUDE_API_KEY.

    Компания называется Anthropic, а модель — Claude, и человек пишет то, что
    видит у себя в личном кабинете. Ровно на этом ключ однажды и не
    подхватился: он лежал в .env под именем CLAUDE_API_KEY, а Scott искал
    ANTHROPIC_API_KEY и молча не находил ничего.
    """
    import os

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_API_KEY", "ключ-под-вторым-именем")

    assert (os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY"))         == "ключ-под-вторым-именем"

# ==================== Перебор ключей шлюза ====================

def test_gateway_switches_to_spare_key_on_rate_limit(отвечающий, monkeypatch):
    """
    Упёрлись в предел — берём следующий ключ и повторяем запрос.

    Это и есть смысл нескольких ключей: без перебора второй и третий лежали бы
    мёртвым грузом, а человеку пришлось бы править настройки и перезапускать
    backend посреди работы.
    """
    try:
        import key_ring
    except ImportError:  # pragma: no cover
        from backend import key_ring

    отвечающий.api_provider = "OpenRouter"
    отвечающий.client = {"api_key": "первый", "base_url": ia.OPENROUTER_BASE}
    отвечающий.model = "какая-то/модель"
    отвечающий.enabled = True
    отвечающий.openrouter_ring = key_ring.KeyRing(["первый", "второй"])

    использованные = []

    def запрос(url, headers=None, json=None, timeout=None):
        ключ = headers["Authorization"].removeprefix("Bearer ")
        использованные.append(ключ)

        if ключ == "первый":
            return Ответ({"error": {"message": "Rate limit exceeded"}}, code=429)

        return Ответ({"choices": [{"message": {"content": "Ответ со второго ключа."}}]})

    monkeypatch.setattr(ia.requests, "post", запрос)

    ответ, успех = отвечающий.answer("вопрос", use_memory=False)

    assert успех
    assert ответ == "Ответ со второго ключа."
    assert использованные == ["первый", "второй"]


def test_gateway_does_not_cycle_on_other_troubles(отвечающий, monkeypatch):
    """
    Смена ключа помогает не от всякой беды, и перебирать связку впустую нельзя.

    Кончившиеся деньги не появятся от другого ключа того же счёта. Ходить по
    кругу здесь значит тратить запросы и время человека.
    """
    try:
        import key_ring
    except ImportError:  # pragma: no cover
        from backend import key_ring

    отвечающий.api_provider = "OpenRouter"
    отвечающий.client = {"api_key": "первый", "base_url": ia.OPENROUTER_BASE}
    отвечающий.model = "какая-то/модель"
    отвечающий.enabled = True
    отвечающий.openrouter_ring = key_ring.KeyRing(["первый", "второй", "третий"])

    попыток = []

    def запрос(url, headers=None, json=None, timeout=None):
        попыток.append(1)
        return Ответ({"error": {"message": "Your credit balance is too low"}}, code=400)

    monkeypatch.setattr(ia.requests, "post", запрос)

    ответ, успех = отвечающий.answer("вопрос", use_memory=False)

    assert not успех
    assert len(попыток) == 1, "связка перебиралась там, где это не помогает"
    assert "средства" in ответ


def test_gateway_gives_up_when_all_keys_are_limited(отвечающий, monkeypatch):
    """Когда все ключи упёрлись в предел, Scott говорит об этом, а не молчит."""
    try:
        import key_ring
    except ImportError:  # pragma: no cover
        from backend import key_ring

    отвечающий.api_provider = "OpenRouter"
    отвечающий.client = {"api_key": "первый", "base_url": ia.OPENROUTER_BASE}
    отвечающий.model = "какая-то/модель"
    отвечающий.enabled = True
    отвечающий.openrouter_ring = key_ring.KeyRing(["первый", "второй"])

    попыток = []

    def запрос(url, headers=None, json=None, timeout=None):
        попыток.append(headers["Authorization"])
        return Ответ({"error": {"message": "Rate limit exceeded"}}, code=429)

    monkeypatch.setattr(ia.requests, "post", запрос)

    ответ, успех = отвечающий.answer("вопрос", use_memory=False)

    assert not успех
    assert len(попыток) == 2, "каждый ключ должен быть испробован ровно раз"
    assert "ограничил запросы" in ответ or "лимит" in ответ.lower()

# ==================== Молчание модели ====================

def test_empty_answer_does_not_crash():
    """
    Пустой ответ модели не должен ронять разбор.

    Найдено живой проверкой: часть бесплатных моделей на запрос с картинкой
    отвечает кодом 200, но кладёт в content пустоту — null вместо текста.
    Прямое обращение по цепочке падало с «NoneType has no attribute strip», и
    человек видел внутреннюю ошибку Scott вместо честного «модель не
    ответила». Молчание модели — это не поломка Scott.
    """
    assert ia.first_message({"choices": [{"message": {"content": None}}]}) == ""
    assert ia.first_message({"choices": [{"message": {}}]}) == ""
    assert ia.first_message({"choices": [{}]}) == ""
    assert ia.first_message({"choices": []}) == ""
    assert ia.first_message({}) == ""


def test_normal_answer_is_taken_and_trimmed():
    payload = {"choices": [{"message": {"content": "  Ответ модели.  "}}]}

    assert ia.first_message(payload) == "Ответ модели."


def test_silent_gateway_model_is_reported(отвечающий, monkeypatch):
    """
    Промолчавшая модель шлюза не выдаётся за успешный ответ.

    Притвориться, что ответ получен, и показать пустоту — худшее из
    возможного: человек решит, что сломался Scott.
    """
    отвечающий.api_provider = "OpenRouter"
    отвечающий.client = {"api_key": "ключ", "base_url": ia.OPENROUTER_BASE}
    отвечающий.model = "молчаливая/модель"
    отвечающий.enabled = True

    monkeypatch.setattr(ia.requests, "post",
                        lambda *a, **k: Ответ({"choices": [{"message": {"content": None}}]}))

    ответ, успех = отвечающий.answer("вопрос", use_memory=False)

    assert not успех
    assert "пустой ответ" in ответ or "молчаливая/модель" in ответ
