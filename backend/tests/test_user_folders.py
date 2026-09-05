"""
Открытие папок пользователя.

«Открой загрузки» — просьба про каталог, а не про программу с таким названием.
Раньше такие фразы уходили в поиск приложений и заканчивались бесполезным
«Не нашёл установленное приложение „папку загрузки“».

Сложность тут в неоднозначности, и проверки идут парами. «Фотографии» и
«Музыка» есть в меню Пуск как приложения, и на просьбу «открой фотографии»
человек скорее ждёт программу. Поэтому такие слова считаются папкой, только
если сказано «папка»; однозначные — «загрузки», «рабочий стол» — срабатывают
сразу.
"""

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def actions():
    import os_actions

    return os_actions


@pytest.fixture
def intent():
    from fast_intent import get_fast_intent_engine

    return get_fast_intent_engine()


# ==================== Однозначные папки ====================

@pytest.mark.parametrize("phrase,expected", [
    ("открой загрузки", "downloads"),
    ("открой папку загрузки", "downloads"),
    ("открой рабочий стол", "desktop"),
    ("открой скачанные", "downloads"),
])
def test_unambiguous_folders(intent, phrase, expected):
    """Слова, которыми не называют программы, распознаются сразу."""
    result = intent.detect(phrase)

    assert result.intent_type == "open_folder", f"«{phrase}» не распознано как папка"
    assert result.main_param == expected


# ==================== Спорные: папка только при явном указании ====================

@pytest.mark.parametrize("phrase,expected", [
    ("открой папку с музыкой", "music"),
    ("открой папку документы", "documents"),
    ("открой папку с фотографиями", "pictures"),
])
def test_ambiguous_with_explicit_word(intent, phrase, expected):
    """Со словом «папка» спорные названия означают каталог."""
    result = intent.detect(phrase)

    assert result.intent_type == "open_folder"
    assert result.main_param == expected


@pytest.mark.parametrize("phrase", [
    "открой фотографии",
    "открой музыку",
])
def test_ambiguous_without_explicit_word_is_an_app(intent, phrase):
    """
    Без слова «папка» спорное название — это приложение.

    «Фотографии» есть в меню Пуск, и подменять программу каталогом значило бы
    делать не то, о чём просили. Проверено на живой машине: приложение с таким
    именем в каталоге действительно есть.
    """
    assert intent.detect(phrase).intent_type == "open_app"


@pytest.mark.parametrize("phrase", ["открой блокнот", "открой chrome", "запусти телеграм"])
def test_apps_still_open_as_apps(intent, phrase):
    """Обычные приложения не должны пострадать от правил про папки."""
    assert intent.detect(phrase).intent_type == "open_app"


# ==================== Пути ====================

@pytest.mark.parametrize("key", ["downloads", "documents", "desktop", "pictures", "home"])
def test_folder_paths_resolve(actions, key):
    """Для каждой известной папки находится путь."""
    path = actions.user_folder(key)

    assert path, f"не найден путь для «{key}»"
    assert str(actions.Path.home()) in path


def test_unknown_folder_is_rejected(actions):
    """Незнакомое имя не превращается в случайный путь."""
    assert actions.user_folder("такой-папки-нет") is None

    result = actions.open_user_folder("такой-папки-нет")
    assert not result["success"]


def test_missing_folder_reports_honestly(actions, monkeypatch):
    """
    Отсутствующая папка — честная ошибка, а не «успешно открыл».

    Каталога может не быть: пользователь переименовал его или система собрана
    без стандартных папок.
    """
    monkeypatch.setattr(actions, "user_folder", lambda key: "/такого/пути/точно/нет")

    result = actions.open_user_folder("downloads")

    assert not result["success"]
    assert "не найдена" in result["error"].lower()
