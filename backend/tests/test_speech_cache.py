"""
Заранее озвученные реплики.

Синтез короткой фразы даже после прогрева моделей стоит около четырёхсот
миллисекунд — замер на живой машине; из кэша та же фраза достаётся за треть
миллисекунды. Немного, но эти реплики звучат после каждой команды: «Готово,
сэр», «Выполнено успешно», «Секунду».

Кэш лежит на диске и переживает перезапуск, так что платится это один раз за
всю жизнь установки: первый прогон занял 3.4 секунды, повторный — сотую долю.
"""

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def кэш():
    try:
        import speech_cache
    except ImportError:  # pragma: no cover — запуск из корня репозитория
        from backend import speech_cache
    return speech_cache


class ГолосЗаглушка:
    """Считает, что у него просили озвучить, но ничего не синтезирует."""

    def __init__(self, ломается_на=()):
        self.озвучено = []
        self.ломается_на = set(ломается_на)

    def speak_to_file(self, text):
        if text in self.ломается_на:
            raise RuntimeError("движок не справился")
        self.озвучено.append(text)
        return f"/tmp/{len(self.озвучено)}.wav"


# ==================== Что попадает в набор ====================

def test_stock_phrases_not_empty(кэш):
    """Набор не должен оказаться пустым: тогда прогрев ничего не делает."""
    assert len(кэш.stock_phrases()) > 5


def test_stock_phrases_come_from_the_real_sources(кэш):
    """
    Реплики берутся оттуда же, откуда их берёт сам Scott.

    Переписать их сюда списком было бы проще, но копия разошлась бы с
    оригиналом на первой же правке — ровно как это уже случилось со словарями
    движков разбора, где одни и те же слова лежали в трёх местах и жили своей
    жизнью.
    """
    try:
        from scott_profile import get_scott_profile
        from question_answerer import QuestionAnswerer
    except ImportError:  # pragma: no cover
        from backend.scott_profile import get_scott_profile
        from backend.question_answerer import QuestionAnswerer

    набор = set(кэш.stock_phrases())

    успех = get_scott_profile().profile["responses"]["success"]
    assert набор.issuperset(успех), "ответы об успехе не попали в набор"

    приветствия = QuestionAnswerer.GREETING_RESPONSES.values()
    assert набор.issuperset(приветствия), "приветствия не попали в набор"


def test_no_duplicates_and_no_blanks(кэш):
    """
    Повторов нет, пустых строк нет.

    Одна и та же фраза приходит из двух мест — озвучивать её дважды незачем, а
    пустую нечем.
    """
    набор = кэш.stock_phrases()

    assert len(набор) == len(set(набор)), "в наборе есть повторы"
    assert all(фраза.strip() for фраза in набор), "в наборе есть пустая строка"


def test_only_short_phrases(кэш):
    """
    Длинные ответы в набор не попадают.

    Их бесконечно много, а звучат они по одному разу — заполнять ими диск
    бессмысленно.
    """
    длинные = [ф for ф in кэш.stock_phrases() if len(ф) > 120]
    assert not длинные, f"в наборе длинные ответы: {длинные}"


# ==================== Сам прогрев ====================

def test_warm_speaks_every_phrase(кэш):
    """Прогрев проходит по всему набору, а не по первой фразе."""
    голос = ГолосЗаглушка()
    фразы = ["Готово.", "Выполнено.", "Секунду."]

    сводка = кэш.warm(voice=голос, phrases=фразы)

    assert голос.озвучено == фразы
    assert сводка["prepared"] == 3
    assert сводка["failed"] == 0


def test_one_bad_phrase_does_not_stop_the_rest(кэш):
    """
    Неудача на одной фразе не бросает остальные.

    Скорее всего дело в ней самой, а не в движке, — и остаться из-за неё без
    всего набора было бы обидно.
    """
    голос = ГолосЗаглушка(ломается_на=["Выполнено."])
    фразы = ["Готово.", "Выполнено.", "Секунду."]

    сводка = кэш.warm(voice=голос, phrases=фразы)

    assert голос.озвучено == ["Готово.", "Секунду."]
    assert сводка["prepared"] == 2
    assert сводка["failed"] == 1


def test_warm_never_raises(кэш):
    """
    Прогрев не должен ронять запуск.

    Он дело необязательное: без него Scott просто заговорит на четыреста
    миллисекунд позже, а вот упавший при старте backend — это программа,
    которая не работает вовсе.
    """
    class СовсемСломанный:
        def speak_to_file(self, text):
            raise RuntimeError("движка нет")

    сводка = кэш.warm(voice=СовсемСломанный(), phrases=["Готово."])

    assert сводка["failed"] == 1
    assert сводка["prepared"] == 0
