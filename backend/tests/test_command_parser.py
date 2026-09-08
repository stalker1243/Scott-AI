"""
Выбор типа команды: открыть, закрыть или что-то ещё.

Живая жалоба первого пользователя: «бывают случаи, когда ScottAI не может
закрыть приложение, когда его просят». Причина оказалась в разборщике. Очки за
запуск программы считались сырыми — два за глагол, плюс три за упоминание
знакомой программы, — а у всех остальных типов приводились к отрезку от нуля
до единицы. Сравнивались они напрямую, поэтому «открыть» побеждало всегда,
стоило человеку назвать программу по имени: «закрой дискорд» уходило запускать
дискорд.

Тесты держат обе стороны: и что закрытие больше не подменяется запуском, и что
запуск при этом продолжает работать.
"""

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def parser():
    try:
        from command_parser import CommandParser
    except ImportError:
        from backend.command_parser import CommandParser

    return CommandParser()


# ==================== Закрыть, а не открыть ====================

@pytest.mark.parametrize("phrase,name", [
    ("закрой дискорд", "дискорд"),
    ("закрой браузер", "браузер"),
    ("выключи спотифай", "спотифай"),
    ("заверши хром", "хром"),
    ("закрой телеграм", "телеграм"),
])
def test_close_is_not_launch(parser, phrase, name):
    """
    Просьба закрыть программу не должна её запускать.

    Худший из возможных исходов: человек просит закрыть, а программа
    открывается — и он повторяет просьбу, получая ещё одно окно.
    """
    parsed = parser.parse(phrase)
    assert parsed.command_type == "close_app", f"«{phrase}» -> {parsed.command_type}"
    assert parsed.main_param == name


def test_prefix_does_not_flip_meaning(parser):
    """
    «Выключи» — не «включи» с приставкой.

    Слово искалось простым вхождением, а «включи» лежит внутри «выключи»
    целиком. Просьба выключить музыку читалась как просьба её включить —
    противоположно сказанному.
    """
    assert parser.parse("выключи музыку").command_type == "close_app"
    assert parser.parse("включи музыку").command_type == "open_app"


# ==================== Запуск продолжает работать ====================

@pytest.mark.parametrize("phrase,name", [
    ("открой браузер", "браузер"),
    ("запусти блокнот", "блокнот"),
    ("включи спотифай", "спотифай"),
    ("открой телеграм", "телеграм"),
])
def test_launch_still_recognised(parser, phrase, name):
    """Пара к тестам выше: починка не должна была сломать запуск."""
    parsed = parser.parse(phrase)
    assert parsed.command_type == "open_app", f"«{phrase}» -> {parsed.command_type}"
    assert parsed.main_param == name


def test_bare_app_name_means_launch(parser):
    """
    Одно название без глагола — просьба открыть.

    Сказав просто «дискорд», человек ждёт запуска, а не рассказа о программе.
    Но решается это последним, когда ни один другой тип не подошёл: раньше
    именно это правило перебивало все остальные.
    """
    assert parser.parse("дискорд").command_type == "open_app"


# ==================== Шкала уверенности ====================

@pytest.mark.parametrize("phrase", [
    "открой браузер",
    "закрой дискорд",
    "какая погода",
    "сколько времени",
    "дискорд",
])
def test_confidence_stays_in_range(parser, phrase):
    """
    Уверенность — доля от нуля до единицы, как обещано в описании структуры.

    Смешение шкал и было корнем ошибки: сырые очки доходили до пяти и
    несравнимы с долями. Пока все типы считают одинаково, сравнение между ними
    имеет смысл.
    """
    confidence = parser.parse(phrase).confidence
    assert 0.0 <= confidence <= 1.0, f"«{phrase}» -> {confidence}"


def test_named_app_beats_bare_verb(parser):
    """
    Названная программа добавляет уверенности, но не меняет действие.

    Ровно тот случай, где прежняя надбавка в три очка ломала выбор.
    """
    with_name = parser.parse("открой блокнот").confidence
    without_name = parser.parse("открой").confidence
    assert with_name > without_name


# ==================== Команды, не связанные с программами ====================

@pytest.mark.parametrize("phrase,expected", [
    ("какая погода", "get_weather"),
    ("сколько времени", "unknown"),
])
def test_other_types_not_swallowed(parser, phrase, expected):
    """
    Прочие типы должны доживать до сравнения.

    При сырых очках у запуска любой из них проигрывал заранее — это и делало
    ошибку общей, а не частной для закрытия программ.
    """
    assert parser.parse(phrase).command_type == expected
