"""
Узнавание обращения по имени.

Проверки идут парами, как принято в этом проекте для всего, что различает
команду и обычную речь: рядом с фразой, на которую Scott обязан отозваться,
стоит похожая, на которую он отзываться не должен.

Оба набора выросли из живой проверки голосом:

* «Спасибо, Скотт!» проходило мимо — строка заканчивается восклицательным
  знаком, а не именем, и endswith не срабатывал. При этом «открой блокнот,
  Скотт» без знака работало, и разница выглядела необъяснимой.
* «скотч закончился» Scott принимал за обращение с командой «ч закончился»:
  сравнение шло по подстроке, а «скотч» начинается со «скот».
"""

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def trigger():
    from voice_name_trigger import check_voice_trigger

    return check_voice_trigger


# ==================== Scott обязан отозваться ====================

@pytest.mark.parametrize("phrase,command", [
    ("Скотт, открой блокнот", "открой блокнот"),
    ("Скотт открой блокнот", "открой блокнот"),
    ("Скот, сделай громче", "сделай громче"),
])
def test_name_at_start(trigger, phrase, command):
    """Имя в начале — самый частый случай."""
    result = trigger(phrase)
    assert result.has_trigger
    assert result.command_text == command


@pytest.mark.parametrize("phrase,command", [
    ("открой блокнот, Скотт", "открой блокнот"),
    ("Спасибо, Скотт!", "спасибо"),
    ("Как дела, Скотт?", "как дела"),
])
def test_name_at_end(trigger, phrase, command):
    """
    Имя в конце фразы — так говорят не реже.

    Знак препинания после имени раньше всё ломал: пунктуация снималась только
    после того, как имя найдено, а найти его мешала как раз она.
    """
    result = trigger(phrase)
    assert result.has_trigger, f"«{phrase}» не распознано как обращение"
    assert result.command_text == command


@pytest.mark.parametrize("phrase", ["Скотт", "Скотт?", "Скотт!", "скот"])
def test_name_alone_is_still_an_address(trigger, phrase):
    """
    Одно имя без просьбы — тоже обращение.

    Человек позвал, и молчание в ответ выглядит поломкой. Команда при этом
    пустая, и что с этим делать, решает вызывающий код.
    """
    result = trigger(phrase)
    assert result.has_trigger
    assert result.command_text == ""


# ==================== Scott обязан промолчать ====================

@pytest.mark.parametrize("phrase", [
    "скотч закончился",
    "принеси скотч",
    "скотина какая-то",
    "скотный двор это книга",
    "скотоводство развито в степях",
])
def test_words_starting_like_the_name(trigger, phrase):
    """
    Слова, начинающиеся со «скот», обращением не считаются.

    Реальный случай: «скотч закончился» превращался в команду «ч закончился».
    Имя обязано заканчиваться границей слова — это ровно та же ошибка, что уже
    была в правилах команд, где голое существительное перехватывало вопросы.
    """
    assert not trigger(phrase).has_trigger, f"«{phrase}» ошибочно принято за обращение"


@pytest.mark.parametrize("phrase", [
    "какая сегодня погода",
    "я смотрел фильм про шотландию",
    "открой блокнот",
    "",
])
def test_speech_without_name(trigger, phrase):
    """Без имени Scott не реагирует — он слышит комнату целиком."""
    assert not trigger(phrase).has_trigger


def test_command_survives_punctuation(trigger):
    """Из команды убирается пунктуация, оставшаяся от имени."""
    result = trigger("Скотт, открой блокнот.")
    assert result.has_trigger
    assert result.command_text.rstrip(".") == "открой блокнот"
