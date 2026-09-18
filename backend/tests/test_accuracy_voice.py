"""
Точность на слух: доходит ли сказанное до разбора неискажённым.

ЗАЧЕМ ОТДЕЛЬНО ОТ `test_accuracy`. Тот проверяет понимание текста — как если бы
человек набрал фразу в чате. Но голосом Scott умел меньше, и виноват был не
разбор (он у голоса и чата общий), а то, что до разбора доходило: «открой
Google Chrome» записывалось как «открой кукол хром», и искать по такому
названию было нечего.

Здесь цепь замкнута: фраза произносится синтезом, слушается распознаванием и
разбирается. Попаданием считается не дословное совпадение — оно и не нужно, —
а то, что услышанное приводит к ТОМУ ЖЕ решению, что и написанное. Именно это
человек и замечает: сказал голосом, получил не то, что получил бы в чате.

ЧТО ЭТА ПРОВЕРКА НАШЛА СРАЗУ. Whisper слышит «выключи музыку» как «выключим
музыку», а «очисти» как «очистив». Разборщик таких форм не знал, возвращал
unknown, и команда уходила в модель. Обе фразы теперь разбираются верно:
намерению доверяют при провале разбора, а глаголы в образцах берутся по основе.

ПОЧЕМУ НЕ В БЫСТРОМ ПРОГОНЕ. Нужны обе модели и видеокарта, идёт около минуты.
Запуск: `pytest -m slow` или `python accuracy_voice.py`.
"""

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]

try:
    import accuracy_voice
    import understanding
    from command_parser import CommandParser
    from fast_intent import get_fast_intent_engine
    from question_answerer import get_question_answerer
    from speech_to_text import Recognizer
except ImportError:  # pragma: no cover — запуск из корня репозитория
    from backend import accuracy_voice, understanding
    from backend.command_parser import CommandParser
    from backend.fast_intent import get_fast_intent_engine
    from backend.question_answerer import get_question_answerer
    from backend.speech_to_text import Recognizer


# Ниже этого значения слух считается сломанным.
#
# Порог мягче текстового: синтезированная речь ровнее живой, но распознавание
# всё равно иногда меняет форму слова, и требовать здесь ста процентов значило
# бы падать от каждой такой мелочи. Девяносто — та граница, ниже которой уже не
# мелочь, а поломка.
ПОРОГ = 90.0


@pytest.fixture(scope="module")
def итог():
    """
    Один прогон на весь модуль: поднять обе модели и озвучить восемьдесят фраз
    стоит около минуты, и делать это дважды незачем.
    """
    engines = {
        "intent_engine": get_fast_intent_engine(),
        "parser": CommandParser(),
        "answerer": get_question_answerer(),
    }

    распознаватель = Recognizer("small", "cuda")
    распознаватель.load()

    return accuracy_voice.check(understanding, engines, распознаватель)


def test_слух_не_ниже_порога(итог):
    """
    Главное число. Упало — значит между речью и разбором что-то испортилось:
    подсказка распознаванию, словарь произношения или сами образцы команд.
    """
    assert итог["точность"] >= ПОРОГ, "\n" + accuracy_voice.report(итог)


def test_команды_не_теряются_на_слух(итог):
    """
    Худший из промахов: сказанную вслух команду Scott принял за вопрос и ушёл
    рассуждать. Для человека это выглядит как «голосом он не понимает» — ровно
    та жалоба, с которой всё и началось.
    """
    потерянные = [п for п in итог["промахи"]
                  if п["вышло"].startswith("question")
                  and not п["ожидалось"].startswith("question")]

    assert not потерянные, "команды ушли в модель после распознавания:\n" + "\n".join(
        f"  сказано «{п['сказано']}» → услышано «{п['услышано']}»"
        for п in потерянные)
