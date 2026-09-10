"""
Поиск в браузере: что искать и по какому адресу.

Живая жалоба: «команда „введи в поиск браузера что-то“ часто имеет баг».
Дефектов оказалось два, и они независимы — один в разборе, другой в исполнении.

**Разбор.** Из фразы вырезалось только слово «поиск» — единственное, знакомое
хотя бы одному движку. Глагол «введи» и слово «браузера» оставались в запросе,
и Scott искал «введи браузера рецепт борща». Соседние формулировки ломались
заметнее: «введи в поисковик котики» вообще не искало, а «напиши в поиске
браузера новости» уходило в новости с темой «напиши поиске браузера».

**Исполнение.** Запрос подставлялся в адрес как есть. На первом же особом знаке
он молча обрезался: «C# и C++» браузер видел как «C» (всё после решётки он
считает частью адреса), а «кошки & собаки» — как «кошки» (амперсанд начинает
новый параметр). Человек получал результаты не того, о чём спрашивал, и понять
причину не мог.
"""

from urllib.parse import quote_plus

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def разбор():
    try:
        import understanding
        from command_parser import CommandParser
        from fast_intent import get_fast_intent_engine
        from question_answerer import get_question_answerer
    except ImportError:  # pragma: no cover — запуск из корня репозитория
        from backend import understanding
        from backend.command_parser import CommandParser
        from backend.fast_intent import get_fast_intent_engine
        from backend.question_answerer import get_question_answerer

    engines = {
        "intent_engine": get_fast_intent_engine(),
        "parser": CommandParser(),
        "answerer": get_question_answerer(),
    }
    return lambda text: understanding.understand(text, **engines)


# ==================== Что искать ====================

@pytest.mark.parametrize("phrase,query", [
    ("введи в поиск браузера рецепт борща", "рецепт борща"),
    ("введи в поисковик котики", "котики"),
    ("вбей в поиск браузера погоду", "погоду"),
    ("набери в гугле как приготовить пасту", "как приготовить пасту"),
    ("напиши в поиске браузера новости", "новости"),
    ("введи в поиск рецепт борща", "рецепт борща"),
])
def test_search_query_is_clean(разбор, phrase, query):
    """
    В запрос попадает только то, что просили найти.

    Глагол, место («в поиске браузера») и предлоги — часть самой просьбы, а не
    её содержания.
    """
    decision = разбор(phrase)
    assert decision.kind == "action", f"«{phrase}» -> {decision.kind}"
    assert decision.action == "search", f"«{phrase}» -> {decision.action}"
    assert decision.param == query, f"«{phrase}» -> {decision.param!r}"


@pytest.mark.parametrize("phrase", [
    "введи в поиск браузера рецепт борща",
    "напиши в поиске браузера новости",
    "набери в гугле как приготовить пасту",
])
def test_entry_phrase_beats_other_types(разбор, phrase):
    """
    Просьба ввести в поиск сильнее случайных совпадений.

    «Напиши в поиске браузера новости» уходило в новости: слово «новости»
    совпадало с их списком. Выражение «напиши в поиске» многословное, поэтому
    по точности оно перебивает одиночное совпадение.
    """
    assert разбор(phrase).action == "search"


# ==================== По какому адресу ====================

@pytest.fixture
def исполнитель(monkeypatch):
    """Исполнитель с заглушкой вместо браузера: окна открывать не нужно."""
    try:
        import command_executor as module
    except ImportError:  # pragma: no cover
        from backend import command_executor as module

    открытые = []
    monkeypatch.setattr(module.webbrowser, "open", lambda url: открытые.append(url))

    return module.CommandExecutor(), открытые


@pytest.mark.parametrize("query", [
    "рецепт борща",
    "C# и C++",
    "кошки & собаки",
    "что такое #hashtag",
    "python 3.13 release notes",
])
def test_query_is_escaped_in_url(исполнитель, query):
    """
    Запрос кодируется целиком, каким бы он ни был.

    Проверяется не «есть ли вызов quote_plus», а то, что в браузер уходит
    адрес, из которого запрос восстанавливается дословно.
    """
    executor, открытые = исполнитель
    executor.search_browser(query)

    assert открытые, "браузер не открывался"
    url = открытые[0]
    assert url == f"https://www.google.com/search?q={quote_plus(query)}"


@pytest.mark.parametrize("query,broken", [
    ("C# и C++", "C"),
    ("кошки & собаки", "кошки"),
])
def test_special_characters_no_longer_truncate(исполнитель, query, broken):
    """
    Пара к тесту выше: обрезанный запрос в адрес больше не попадает.

    Именно так это и выглядело — поиск по «C» вместо «C# и C++». Ошибки при
    этом не было, и в логе тоже: Scott честно сообщал, что ищет то, о чём
    просили.
    """
    executor, открытые = исполнитель
    executor.search_browser(query)

    assert f"q={broken}&" not in открытые[0]
    assert f"q={broken}#" not in открытые[0]
    assert open_query(открытые[0]) == query


def open_query(url: str) -> str:
    """Достать запрос обратно из адреса — так его увидит браузер."""
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(url).query)["q"][0]
