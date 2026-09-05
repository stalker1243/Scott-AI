"""
Открыть сайт — не то же самое, что искать на нём.

Упоминание сервиса всегда означало поиск, поэтому на «открой ютуб» Scott
отвечал «Не понял, что искать на YouTube» и не открывал ничего.

Проверка идёт через настоящий обработчик команды, а не через вспомогательную
функцию разбора: первая версия этих тестов сама собирала список служебных слов
и потому оставалась зелёной, даже когда ветка в `main.py` была сломана.
Браузер при этом не открывается — вызовы к `web_integrations` подменяются.
"""

import asyncio

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def scott_main():
    import main

    return main


@pytest.fixture(scope="module")
def scott(scott_main):
    return scott_main.ScottAI()


@pytest.fixture
def calls(scott_main, monkeypatch):
    """Подменить веб-интеграции: записываем, что Scott собирался сделать."""
    log = []

    def fake_home(service):
        log.append(("home", service))
        return {"success": True, "message": f"Открываю {service}"}

    def fake_youtube(query):
        log.append(("search_youtube", query))
        return {"success": True, "message": f"поиск: {query}"}

    def fake_github(query):
        log.append(("search_github", query))
        return {"success": True, "message": f"поиск: {query}"}

    web = scott_main.web_integrations
    monkeypatch.setattr(web, "open_service_home", fake_home)
    monkeypatch.setattr(web, "search_youtube_video", fake_youtube)
    monkeypatch.setattr(web, "search_github_repo", fake_github)
    return log


def _run(scott, text):
    return asyncio.run(scott.process_command(text, quiet_mode=True))


@pytest.mark.parametrize("phrase,service", [
    ("открой ютуб", "youtube"),
    ("открой youtube", "youtube"),
    ("запусти ютуб", "youtube"),
    ("открой мне пожалуйста ютуб", "youtube"),
    ("открой youtube в главное меню", "youtube"),
    ("открой гитхаб", "github"),
])
def test_bare_service_opens_home(scott, calls, phrase, service):
    """Просьба без запроса — это просьба открыть сайт."""
    _run(scott, phrase)
    assert calls == [("home", service)], f"«{phrase}» -> {calls}"


@pytest.mark.parametrize("phrase,expected", [
    ("найди на ютубе видео про запуск ракеты", ("search_youtube", "запуск ракеты")),
    ("включи на ютубе музыку для работы", ("search_youtube", "музыку для работы")),
    ("найди на гитхабе репозиторий fastapi", ("search_github", "fastapi")),
])
def test_query_still_searches(scott, calls, phrase, expected):
    """
    Пара к тесту выше: содержательный запрос по-прежнему уходит в поиск.

    Без этой половины «просто открывать сайт» легко сделать так, что поиск
    перестанет работать вовсе.
    """
    _run(scott, phrase)
    assert calls == [expected], f"«{phrase}» -> {calls}"


def test_service_homes_known():
    """У обоих сервисов есть адрес главной — иначе открывать будет нечего."""
    try:
        import web_integrations
    except ImportError:
        from backend import web_integrations

    assert set(web_integrations.SERVICE_HOMES) == {"youtube", "github"}

# ==================== Сайты вместо приложений ====================

@pytest.fixture
def site_calls(scott_main, monkeypatch):
    """Подменить открытие сайта: браузер трогать незачем."""
    log = []

    def fake_site(name):
        import web_integrations as real
        cleaned = name.strip().strip(" .,!?:;—-").lower()
        url = real.KNOWN_SITES.get(cleaned)
        if not url:
            return None
        log.append(cleaned)
        return {"success": True, "message": f"Открываю {cleaned}", "url": url}

    monkeypatch.setattr(scott_main.web_integrations, "open_site", fake_site)
    return log


@pytest.mark.parametrize("name,url", [
    ("гугл", "https://www.google.com"),
    ("вк", "https://vk.com"),
    ("сайт wikipedia", "https://ru.wikipedia.org"),
    ("example.com", "https://example.com"),
    ("ya.ru", "https://ya.ru"),
])
def test_site_recognised(name, url, monkeypatch):
    """
    Название сайта или домен открываются в браузере.

    До этого «открой гугл» уходило искать установленную программу «гугл» и
    заканчивалось отказом: Scott умел открывать приложения и искать внутри
    YouTube, но не умел просто открыть сайт.
    """
    try:
        import web_integrations
    except ImportError:
        from backend import web_integrations

    opened = []
    monkeypatch.setattr(web_integrations.webbrowser, "open", opened.append)

    result = web_integrations.open_site(name)
    assert result is not None, f"«{name}» не распознан как сайт"
    assert result["url"] == url
    assert opened == [url]


@pytest.mark.parametrize("name", [
    "блокнот",
    "ть дельторуна",
    "несуществующую программу",
    "",
])
def test_not_a_site(name, monkeypatch):
    """
    Пара к тесту выше: что не похоже на сайт, браузером не открывается.

    Иначе любая неудача с приложением заканчивалась бы случайной страницей
    вместо честного «не нашёл».
    """
    try:
        import web_integrations
    except ImportError:
        from backend import web_integrations

    opened = []
    monkeypatch.setattr(web_integrations.webbrowser, "open", opened.append)

    assert web_integrations.open_site(name) is None
    assert opened == []


@pytest.fixture
def fake_executor(scott_main, monkeypatch):
    """
    Подменить исполнителя команд: настоящий открыл бы окно на каждом прогоне.

    Возвращает функцию-переключатель — она задаёт, нашлось приложение или нет.
    """
    state = {"found": True}

    class Stub:
        def execute(self, kind, **params):
            if state["found"]:
                return f"✅ Открыл приложение: {params.get('name')}"
            return f"❌ Не нашёл установленное приложение «{params.get('name')}»"

    monkeypatch.setattr(scott_main, "executor", Stub())
    return state


def test_installed_app_wins_over_site(scott, site_calls, fake_executor):
    """
    Установленная программа важнее веб-версии.

    Discord, Telegram и Steam есть и в списке сайтов, и обычно установлены —
    Scott должен открывать программу, а к списку сайтов обращаться только
    когда приложения не нашлось.
    """
    fake_executor["found"] = True
    _run(scott, "открой дискорд")
    assert site_calls == [], "для установленного приложения открывался сайт"


def test_site_used_when_app_missing(scott, site_calls, fake_executor):
    """
    Пара к тесту выше: если программы нет, открывается сайт.

    Ровно этого и не хватало — «открой гугл» заканчивалось отказом «не нашёл
    установленное приложение».
    """
    fake_executor["found"] = False
    _run(scott, "открой гугл")
    assert site_calls == ["гугл"], f"сайт не открылся: {site_calls}"
