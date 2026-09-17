"""
Распознавание речи: две реализации Whisper за одним окошком.

ЧТО ЗАМЕРЕНО. faster-whisper обещает четырёхкратное ускорение. Проверено на
этой машине (RTX 3060, модель small), четыре фразы общей длиной двенадцать
секунд, один и тот же путь через backend:

    openai-whisper   2.25 с
    faster-whisper   1.87 с

То есть быстрее примерно на шестую часть, а не вчетверо. Обещанные четыре раза
относятся к другим связкам. Полсекунды на четырёх фразах человек всё же
замечает, а точность у быстрой оказалась не хуже: «Введи в поиск браузера
рецепт борща» против «Введев поиск браузера, рецепт борща».

ПОЧЕМУ ОБЕ. Быстрая тянет за собой CTranslate2 и скачивает модель в своём
формате. Если её нет или она не завелась, Scott должен продолжать слышать, а
не умолкать.

Модели здесь не загружаются: это секунды и сотни мегабайт. Проверяется выбор
реализации и то, что при любой беде остаётся рабочий путь.
"""

import sys
import types

import pytest

pytestmark = pytest.mark.unit


try:
    import speech_to_text
except ImportError:  # pragma: no cover — запуск из корня репозитория
    from backend import speech_to_text


class ПоддельнаяБыстрая:
    """Подделка faster_whisper.WhisperModel."""

    последний_вызов = {}

    def __init__(self, name, device=None, compute_type=None):
        ПоддельнаяБыстрая.последний_вызов = {
            "name": name, "device": device, "compute_type": compute_type}

    def transcribe(self, audio, language=None, temperature=None, initial_prompt=None):
        # Число попыток запоминается: пять заходов вместо двух — это полторы
        # секунды впустую на каждой записи без внятной речи.
        ПоддельнаяБыстрая.последняя_температура = temperature

        # И подсказка: без неё Whisper слышит «Скот» вместо «Скотт», а каждый
        # непрочитанный вариант имени — это фраза, прошедшая мимо.
        ПоддельнаяБыстрая.последняя_подсказка = initial_prompt

        куски = [types.SimpleNamespace(text="привет "),
                 types.SimpleNamespace(text="мир")]
        return куски, None


class ПоддельнаяОбычная:
    """Подделка модели openai-whisper."""

    def __init__(self, fail_on=None):
        self.fail_on = fail_on
        self.последний = {}

    def transcribe(self, audio, language=None, fp16=None):
        self.последний = {"language": language, "fp16": fp16}
        return {"text": "  привет мир  "}


def подсунуть_быструю(monkeypatch, работает=True):
    модуль = types.ModuleType("faster_whisper")

    if работает:
        модуль.WhisperModel = ПоддельнаяБыстрая
    else:
        def взрыв(*a, **k):
            raise RuntimeError("нет cuDNN")
        модуль.WhisperModel = взрыв

    модуль.__version__ = "1.1.0"
    monkeypatch.setitem(sys.modules, "faster_whisper", модуль)


def подсунуть_обычную(monkeypatch, модель=None):
    модуль = types.ModuleType("whisper")
    готовая = модель or ПоддельнаяОбычная()
    модуль.load_model = lambda name, device=None: готовая
    модуль.__version__ = "20250625"
    monkeypatch.setitem(sys.modules, "whisper", модуль)
    return готовая


# ==================== Выбор реализации ====================

def test_fast_engine_is_preferred(monkeypatch):
    """
    Когда быстрая есть, берётся она: замер показал выигрыш на каждой фразе.
    """
    monkeypatch.setattr(speech_to_text, "ENGINE_CHOICE", "auto")
    подсунуть_быструю(monkeypatch)
    подсунуть_обычную(monkeypatch)

    р = speech_to_text.Recognizer("small", "cuda")

    assert р.load() == "faster-whisper"


def test_falls_back_when_fast_engine_missing(monkeypatch):
    """
    Быстрой нет — Scott продолжает слышать обычной.

    Это главное свойство всей затеи: лишняя библиотека не должна становиться
    условием того, что помощник вообще работает.
    """
    monkeypatch.setattr(speech_to_text, "ENGINE_CHOICE", "auto")
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    подсунуть_обычную(monkeypatch)

    р = speech_to_text.Recognizer("small", "cuda")

    assert р.load() == "openai-whisper"


def test_falls_back_when_fast_engine_breaks(monkeypatch):
    """
    Быстрая есть, но не поднялась — не хватило видеопамяти, нет cuDNN, битый
    кэш модели. Тоже не повод остаться без слуха.
    """
    monkeypatch.setattr(speech_to_text, "ENGINE_CHOICE", "auto")
    подсунуть_быструю(monkeypatch, работает=False)
    подсунуть_обычную(monkeypatch)

    р = speech_to_text.Recognizer("small", "cuda")

    assert р.load() == "openai-whisper"


def test_engine_can_be_chosen_by_hand(monkeypatch):
    """Выбор реализации через настройку: нужно, чтобы сравнивать их вживую."""
    monkeypatch.setattr(speech_to_text, "ENGINE_CHOICE", "openai")
    подсунуть_быструю(monkeypatch)
    подсунуть_обычную(monkeypatch)

    р = speech_to_text.Recognizer("small", "cuda")

    assert р.load() == "openai-whisper"


def test_precision_depends_on_device(monkeypatch):
    """
    На видеокарте float16, на процессоре int8.

    Замер трёх режимов: float16 оказался и самым быстрым, и самым точным, а
    int8 медленнее почти вдвое. На процессоре float16 просто не поддерживается.
    """
    monkeypatch.setattr(speech_to_text, "ENGINE_CHOICE", "faster")
    подсунуть_быструю(monkeypatch)

    speech_to_text.Recognizer("small", "cuda").load()
    assert ПоддельнаяБыстрая.последний_вызов["compute_type"] == "float16"

    speech_to_text.Recognizer("small", "cpu").load()
    assert ПоддельнаяБыстрая.последний_вызов["compute_type"] == "int8"


# ==================== Распознавание ====================

def test_fast_engine_glues_pieces(monkeypatch):
    """
    Быстрая отдаёт ответ кусками, и склеить их нужно самому.

    Взять только первый — значит потерять хвост длинной фразы, а фразы к Scott
    обращают как раз длинные.
    """
    monkeypatch.setattr(speech_to_text, "ENGINE_CHOICE", "faster")
    подсунуть_быструю(monkeypatch)

    р = speech_to_text.Recognizer("small", "cuda")

    assert р.transcribe("звук.wav") == "привет мир"


def test_plain_engine_returns_trimmed_text(monkeypatch):
    monkeypatch.setattr(speech_to_text, "ENGINE_CHOICE", "openai")
    подсунуть_обычную(monkeypatch)

    р = speech_to_text.Recognizer("small", "cuda")

    assert р.transcribe("звук.wav") == "привет мир"


def test_fp16_only_on_gpu(monkeypatch):
    """
    На процессоре fp16 не поддерживается, и whisper предупреждает об этом на
    каждую фразу — в логе становится не видно ничего другого.
    """
    monkeypatch.setattr(speech_to_text, "ENGINE_CHOICE", "openai")
    модель = подсунуть_обычную(monkeypatch)

    speech_to_text.Recognizer("small", "cpu").transcribe("звук.wav")
    assert модель.последний["fp16"] is False

    speech_to_text.Recognizer("small", "cuda").transcribe("звук.wav")
    assert модель.последний["fp16"] is True


def test_model_loads_once(monkeypatch):
    """
    Модель поднимается один раз.

    Раньше она загружалась заново на каждое голосовое сообщение — лишние
    секунды на каждую фразу.
    """
    monkeypatch.setattr(speech_to_text, "ENGINE_CHOICE", "faster")

    загрузок = []

    модуль = types.ModuleType("faster_whisper")

    class Считающая(ПоддельнаяБыстрая):
        def __init__(self, *a, **k):
            загрузок.append(1)
            super().__init__(*a, **k)

    модуль.WhisperModel = Считающая
    monkeypatch.setitem(sys.modules, "faster_whisper", модуль)

    р = speech_to_text.Recognizer("small", "cuda")
    р.transcribe("раз.wav")
    р.transcribe("два.wav")
    р.transcribe("три.wav")

    assert len(загрузок) == 1


# ==================== Диагностика ====================

def test_available_engines_reports_what_is_installed(monkeypatch):
    """
    Человеку, у которого распознавание медленное, полезно видеть, что быстрая
    реализация просто не установлена.
    """
    подсунуть_быструю(monkeypatch)
    подсунуть_обычную(monkeypatch)

    есть = speech_to_text.available_engines()

    assert есть["faster-whisper"]
    assert есть["openai-whisper"]


def test_missing_engine_is_reported_as_empty(monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    подсунуть_обычную(monkeypatch)

    есть = speech_to_text.available_engines()

    assert есть["faster-whisper"] == ""
    assert есть["openai-whisper"]


# ==================== Записи, в которых нет речи ====================
#
# Из 715 записей в живом журнале 429 оказались ровно пятнадцатисекундными —
# длиной в предел фразы у слушателя. Такая запись означает, что тишина после
# речи не наступила: играла музыка, шёл разговор в комнате. Whisper на таком
# материале не набирает уверенности и повторяет распознавание с растущей
# температурой — по умолчанию пять заходов, каждый по 200–350 мс. В журнале
# таких переборов набралось 749: это и есть хвост, из-за которого Scott
# временами «подвисал» на пять секунд и дольше.

def test_попыток_две_а_не_пять(monkeypatch):
    """
    Пять заходов на записи без внятной речи — полторы секунды впустую. Две:
    первая ловит обычную речь, вторая помогает на трудной записи.

    Проверяется то, что уходит в модель, а не значение постоянной: постоянную
    легко объявить и забыть передать.
    """
    import speech_to_text

    подсунуть_быструю(monkeypatch)

    р = speech_to_text.Recognizer("small", "cpu")
    р.load()
    р.transcribe("запись.wav")

    assert ПоддельнаяБыстрая.последняя_температура == [0.0, 0.2]


def test_имя_подсказывается_распознаванию(monkeypatch):
    """
    Whisper склоняется к словам из подсказки. Нам это нужно ровно в одном
    месте — в имени: без подсказки «Скотт, какая погода» распознаётся как
    «Скот, какая погода», а на живой речи вариантов больше, и каждый
    непрочитанный означает, что человека не услышали вовсе.
    """
    import speech_to_text

    подсунуть_быструю(monkeypatch)

    р = speech_to_text.Recognizer("small", "cpu")
    р.load()
    р.transcribe("запись.wav")

    assert "Скотт" in (ПоддельнаяБыстрая.последняя_подсказка or "")


def test_короткая_запись_не_проверяется_на_речь():
    """
    Проверка стоит около ста миллисекунд. Для команды в полторы секунды это
    прибавка ни за что: человек говорил, речь там есть.
    """
    import numpy as np
    import speech_to_text

    р = speech_to_text.Recognizer("small", "cpu")

    assert р._есть_речь(np.zeros(16000, dtype=np.float32))


def test_путь_к_файлу_проверку_проходит():
    """Загруженная запись — не фон из комнаты, и длину её дёшево не узнать."""
    import speech_to_text

    р = speech_to_text.Recognizer("small", "cpu")

    assert р._есть_речь("запись.wav")


def test_при_сбое_проверки_считаем_что_речь_есть(monkeypatch):
    """
    Самое важное здесь. Пропустить команду хуже, чем лишний раз её поискать,
    поэтому любое сомнение решается в пользу распознавания.
    """
    import numpy as np
    import speech_to_text

    def падает(*а, **к):
        raise RuntimeError("модель определения речи не завелась")

    monkeypatch.setattr("faster_whisper.vad.get_speech_timestamps", падает)

    р = speech_to_text.Recognizer("small", "cpu")
    длинная = np.zeros(16000 * 15, dtype=np.float32)

    assert р._есть_речь(длинная)


# ==================== Что Whisper выдумывает ====================
#
# На тишине и шуме он выдаёт обрывки титров из обучающих данных. Это не сбой, а
# известная его черта: модель училась на видео с субтитрами. В журнале
# услышанного такая строка встретилась дословно — «Редактор субтитров
# О.Голубкина», — и Scott честно попытался счесть её командой.

@pytest.mark.parametrize("выдумка", [
    "Редактор субтитров О.Голубкина",
    "Корректор А.Егорова",
    "Субтитры сделал DimaTorzok",
    "Продолжение следует...",
    "Спасибо за просмотр!",
    "Подписывайтесь на канал",
])
def test_выдумка_модели_опознаётся(выдумка):
    import speech_to_text

    assert speech_to_text.looks_like_hallucination(выдумка)


@pytest.mark.parametrize("сказанное", [
    "открой субтитры",
    "Скотт, открой браузер",
    "покажи редактор субтитров в проекте",
    "продолжи работу",
])
def test_сказанное_человеком_не_отбрасывается(сказанное):
    """
    Пара к проверке выше, и она важнее: «открой субтитры» — законная просьба, и
    отбросить её значило бы сделать Scott глухим к целому семейству команд.
    Поэтому выдумки опознаются по началу фразы, а не по вхождению слова.
    """
    import speech_to_text

    assert not speech_to_text.looks_like_hallucination(сказанное)


def test_проверка_речи_достаёт_короткие_записи():
    """
    Порог был пять секунд, и выдумка на записи в 3,4 секунды его не достала —
    ровно та, что нашлась в журнале.
    """
    import speech_to_text

    assert speech_to_text.SPEECH_CHECK_FROM_SECONDS <= 3.0
