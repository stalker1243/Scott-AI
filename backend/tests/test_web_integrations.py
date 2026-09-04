"""
Поиск на YouTube и GitHub не должен зависеть от наличия ключа.

Раньше без YOUTUBE_API_KEY команда «найди на ютубе...» просто не работала:
Scott отвечал инструкцией, как получить ключ в Google Cloud Console, и на этом
всё заканчивалось. Ключ должен улучшать команду (открывать сразу нужный ролик),
а не быть условием её работы — без него открывается страница результатов, и
пользователю остаётся один клик.

Браузер в тестах не открывается: webbrowser.open подменяется, чтобы прогон не
раскидывал вкладки по экрану.
"""

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def web(monkeypatch):
    """Модуль веб-интеграций с перехваченным открытием браузера."""
    import web_integrations

    opened = []
    monkeypatch.setattr(web_integrations.webbrowser, "open", lambda url: opened.append(url))
    web_integrations.opened_urls = opened
    return web_integrations


def test_youtube_without_key_opens_search_page(web, monkeypatch):
    """Без ключа команда работает: открывается страница результатов."""
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)

    result = web.search_youtube_video("группа кино кукушка")

    assert result["success"], "Отсутствие ключа не должно ломать команду"
    assert result["via"] == "search_page"
    assert web.opened_urls, "Браузер не открыли вовсе"
    assert "youtube.com/results?search_query=" in web.opened_urls[-1]


def test_youtube_query_is_url_encoded(web, monkeypatch):
    """
    Кириллица в запросе кодируется.

    Без quote_plus ссылка на «группа кино» разъезжается по пробелу, и браузер
    получает обрезанный запрос.
    """
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)

    web.search_youtube_video("тест запроса")

    url = web.opened_urls[-1]
    assert " " not in url
    assert "%D1%82" in url, "Кириллица не закодирована"


def test_youtube_falls_back_when_api_fails(web, monkeypatch):
    """
    Сбой API — тоже повод открыть страницу результатов, а не отказать.

    Так команда переживает исчерпанную квоту (10 000 единиц в сутки, поиск
    стоит 100), отозванный ключ и недоступность googleapis.com.
    """
    monkeypatch.setenv("YOUTUBE_API_KEY", "ключ-который-не-сработает")

    def explode(*args, **kwargs):
        raise RuntimeError("сеть недоступна")

    monkeypatch.setattr(web.requests, "get", explode)

    result = web.search_youtube_video("что угодно")

    assert result["success"]
    assert result["via"] == "search_page"
    assert "недоступен" in result["reason"]


def test_github_falls_back_when_api_fails(web, monkeypatch):
    """У GitHub тот же запасной путь: страница поиска вместо отказа."""
    def explode(*args, **kwargs):
        raise RuntimeError("сеть недоступна")

    monkeypatch.setattr(web.requests, "get", explode)

    result = web.search_github_repo("fastapi")

    assert result["success"]
    assert result["via"] == "search_page"
    assert "github.com/search?q=" in web.opened_urls[-1]


@pytest.mark.parametrize("query", ["", "   "])
def test_empty_query_is_rejected(web, query):
    """Пустой запрос — единственный случай, когда отказ уместен: искать нечего."""
    assert not web.search_youtube_video(query)["success"]
    assert not web.search_github_repo(query)["success"]
    assert not web.opened_urls, "Браузер открывать не следовало"
