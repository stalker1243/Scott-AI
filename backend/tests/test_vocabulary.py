"""
Словари движков не должны разъезжаться.

Слова, по которым Scott узнаёт, о чём его просят, лежали в трёх модулях сразу:
глаголы запуска — в четырёх списках, слова поиска — в трёх, названия знакомых
программ — в двух. Списки жили своей жизнью, и правка в одном молча оставляла
остальные позади.

Чем это кончалось на деле:

* «yandex котики» роняло обработку с «'IntentResult' object has no attribute
  'lower'»: слово знал разборщик, а список явного поиска — нет, и фраза уходила
  в ветку, которой не следовало доставаться никому;
* «зайди на ютуб» искало на YouTube слово «зайди»: глагол перехода был в
  списке GitHub, а у YouTube его забыли;
* в списке знакомых программ у одного движка были русские названия, у другого
  только английские.

Теперь роль описана в `vocabulary.py` один раз, а движки её берут. Эти тесты
следят, чтобы копии не завелись снова: любая из них проживёт до первой правки
общего списка, после чего движки начнут понимать одну и ту же фразу по-разному.
"""

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def модули():
    try:
        import command_parser
        import fast_intent
        import understanding
        import vocabulary
    except ImportError:  # pragma: no cover — запуск из корня репозитория
        from backend import command_parser, fast_intent, understanding, vocabulary

    return {
        "vocabulary": vocabulary,
        "intent": fast_intent.FastIntentEngine,
        "parser": command_parser.CommandParser,
        "understanding": understanding,
    }


# ==================== Один источник на роль ====================

def test_launch_verbs_shared(модули):
    """
    Глаголы запуска — один список на всех.

    Их было четыре: у движка намерений, дважды у разборщика и у решения. У
    намерений при этом не было вежливых форм «откройте» и «запустите».
    """
    словарь = модули["vocabulary"]
    глаголы = set(словарь.LAUNCH_VERBS)

    assert set(модули["intent"].OPEN_APP_PHRASES) == глаголы
    assert set(модули["parser"].OPEN_APP_VERBS) == глаголы
    assert глаголы <= set(модули["parser"].COMMAND_SYNONYMS["open_app"])


def test_close_verbs_shared(модули):
    """Глаголы закрытия — тоже один список."""
    глаголы = set(модули["vocabulary"].CLOSE_VERBS)

    assert set(модули["intent"].CLOSE_APP_PHRASES) == глаголы
    assert set(модули["parser"].COMMAND_SYNONYMS["close_app"]) == глаголы


def test_app_names_shared(модули):
    """
    Названия программ известны всем одинаково.

    У решения в этом списке были только английские названия: «discord» оно
    узнавало, а «дискорд» — нет.
    """
    названия = set(модули["vocabulary"].KNOWN_APP_NAMES)

    assert set(модули["parser"].KNOWN_APP_NAMES) == названия
    assert set(модули["understanding"].KNOWN_APP_NAMES) == названия

    # Проверка по существу, а не только на равенство списков: русские
    # названия обязаны быть, иначе равенство ничего не значит.
    for название in ("дискорд", "блокнот", "браузер", "телеграм"):
        assert название in названия


def test_search_words_shared(модули):
    """
    Слова поиска: разборщик и проверка «явного поиска» обязаны совпадать.

    Именно расхождение этих двух списков открыло путь к сбою. Движок намерений
    может знать больше — у него есть слабые подсказки вроде «посмотри», —
    но не меньше.
    """
    словарь = модули["vocabulary"]
    строгие = set(словарь.SEARCH_WORDS)

    assert set(модули["parser"].COMMAND_SYNONYMS["search"]) == строгие
    assert set(модули["understanding"].EXPLICIT_SEARCH_WORDS) == строгие
    assert строгие <= set(модули["intent"].SEARCH_PHRASES)


def test_weak_hints_stay_out_of_strict_list(модули):
    """
    Пара к тесту выше: слабые подсказки в строгий список не попадают.

    «Посмотри» с равным успехом означает «поищи в интернете» и «посмотри
    процессы». Попади оно в строгий список — отменило бы переопределение
    «разобрано как поиск, но по форме это вопрос», и «посмотри, что такое
    фотосинтез» ушло бы искать вместо ответа.
    """
    словарь = модули["vocabulary"]

    for подсказка in словарь.WEAK_SEARCH_HINTS:
        assert подсказка not in словарь.SEARCH_WORDS


def test_create_phrases_shared(модули):
    """Что создавать — файл или папку — решается по одному списку."""
    словарь = модули["vocabulary"]
    всё = set(словарь.CREATE_FILE_PHRASES) | set(словарь.CREATE_FOLDER_PHRASES)

    assert set(модули["intent"].CREATE_FILE_PHRASES) == всё
    assert set(модули["parser"].COMMAND_SYNONYMS["create_file"]) == set(словарь.CREATE_FILE_PHRASES)
    assert set(модули["parser"].COMMAND_SYNONYMS["create_folder"]) == set(словарь.CREATE_FOLDER_PHRASES)


def test_create_needs_an_object(модули):
    """
    Голых «создай» и «создать» в списках нет.

    С ними любая просьба что-нибудь сделать превращалась в файл или папку:
    «создай программу занятий для новичка» заводило пустой файл с таким именем
    и рапортовало об успехе.
    """
    словарь = модули["vocabulary"]
    все_фразы = словарь.CREATE_FILE_PHRASES + словарь.CREATE_FOLDER_PHRASES

    for голое in ("создай", "создать", "напиши", "сделай"):
        assert голое not in все_фразы, f"«{голое}» без объекта снова в списке"


def test_question_words_shared(модули):
    """Вопросительные слова — один список на движок намерений и на решение."""
    слова = set(модули["vocabulary"].QUESTION_WORDS)

    assert set(модули["intent"].QUESTION_WORDS) == слова
    assert set(модули["understanding"].QUESTION_KEYWORDS) == слова


# ==================== Совпадение по границам слова ====================

@pytest.mark.parametrize("text,word,expected", [
    ("выключи музыку", "включи", False),
    ("включи музыку", "включи", True),
    ("запустить дельторуна", "запусти", False),
    ("запусти дельторуна", "запусти", True),
    ("подключи наушники", "ключи", False),
    ("где мои ключи", "ключи", True),
])
def test_word_boundaries(модули, text, word, expected):
    """
    Слово ищется целиком, а не куском другого слова.

    Простое вхождение стоило двух дефектов: «включи» находится внутри
    «ВЫключи», и просьба выключить музыку читалась как просьба её включить; а
    синоним «запусти» находился внутри «запустить», и резолвер получал на вход
    «ть дельторуна».
    """
    assert модули["vocabulary"].has_word(text, word) is expected


def test_empty_word_matches_nothing(модули):
    """
    Пустая строка не совпадает ни с чем.

    Такое уже ловили в поиске процессов: пустое имя совпадало с любым
    запросом, потому что `"".startswith("")` — истина.
    """
    assert модули["vocabulary"].has_word("открой браузер", "") is False
