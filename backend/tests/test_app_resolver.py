"""
Поиск приложения по названию.

Проверяется чистая функция сходства, а не сам запуск: каталог установленных
программ у каждой машины свой, и тест, зависящий от него, ничего бы не
доказывал.
"""

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def resolver():
    try:
        import app_resolver
    except ImportError:
        from backend import app_resolver

    return app_resolver


@pytest.mark.parametrize("query,catalog_name", [
    ("discord", "discord"),
    ("firefox", "firefox web browser"),
    ("chrome", "google chrome"),
    ("visual studio", "visual studio code"),
])
def test_short_query_matches_app(resolver, query, catalog_name):
    """Обычный запрос по-прежнему находит программу — в том числе по части названия."""
    assert resolver._similarity(query, catalog_name) >= resolver.MIN_FUZZY_SCORE


@pytest.mark.parametrize("phrase", [
    "напомним мне 1800, зайти discord",
    "напомни вечером написать другу в телеграм",
    "запиши в заметки что нужно обновить discord",
])
def test_long_phrase_does_not_match_app(resolver, phrase):
    """
    Пара к тесту выше — и случай из живого лога.

    Название программы, случайно упомянутое посреди длинной фразы, давало
    сходство 0.85 и приложение запускалось: на просьбу поставить напоминание
    Scott открыл Discord прямо сейчас. Название внутри запроса теперь
    засчитывается только тогда, когда сам запрос не длиннее названия вдвое.
    """
    for app in ("discord", "телеграм"):
        assert resolver._similarity(phrase, app) < resolver.MIN_FUZZY_SCORE, \
            f"«{phrase}» ошибочно похожа на «{app}»"


# ==================== Русское произношение латинских названий ====================

@pytest.mark.parametrize("spoken,expected", [
    ("дельтарун", "deltarun"),
    ("дискорд", "diskord"),
    ("стим", "stim"),
    ("фотошоп", "fotoshop"),
])
def test_transliteration(resolver, spoken, expected):
    """Кириллица переводится в латиницу — иначе сравнивать не с чем."""
    assert resolver.transliterate(spoken) == expected


@pytest.mark.parametrize("spoken,catalog_name", [
    ("дельторуна", "deltarune"),
    ("дискорд", "discord"),
    ("фотошоп", "photoshop"),
])
def test_spoken_russian_matches_latin_app(resolver, spoken, catalog_name):
    """
    Названия человек произносит по-русски, а каталог Windows хранит их
    латиницей — и посимвольное сравнение двух алфавитов давало почти ноль.

    Случай из живого лога: «запустить дельторуна» (Whisper ещё и переврал
    гласную) не находило установленную игру Deltarune.

    Совсем короткие названия («стим» → steam) транслитерация не вытягивает —
    четыре буквы против пяти дают 0.67 при пороге 0.72. Для них по-прежнему
    работает список ALIASES; транслитерация нужна для всего остального, чего
    в списке заведомо нет.
    """
    best = max(
        resolver._similarity(variant, catalog_name)
        for variant in resolver._search_variants(spoken)
    )
    assert best >= resolver.MIN_FUZZY_SCORE, f"«{spoken}» не дотянулась до «{catalog_name}»"


def test_case_ending_stripped_only_when_word_remains(resolver):
    """
    Падежное окончание снимается, но не в ущерб коротким названиям: у «игры»
    убрать «ы» — значит превратить запрос в бессмыслицу.
    """
    variants = resolver._search_variants("дельтаруна")
    assert "deltarun" in variants or "дельтарун" in variants
    assert resolver._strip_case_ending("игры") == "игры"
