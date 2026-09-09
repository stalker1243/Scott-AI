"""
Разделение вопросов и команд.

Самый крупный модуль backend (719 строк) не был покрыт ничем, а решает он
вещь, от которой зависит вообще всё: считать сказанное вопросом — и отправить
в LLM — или командой, которую надо выполнить. Ошибка в любую сторону ломает
Scott целиком: либо он перестаёт открывать программы, либо начинает открывать
их в ответ на разговор.

Ответы, требующие похода в сеть, здесь не проверяются — только границы и
локальные сведения о машине.
"""

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def qa():
    try:
        from question_answerer import QuestionAnswerer
    except ImportError:
        from backend.question_answerer import QuestionAnswerer

    return QuestionAnswerer()


# ==================== Вопрос или команда ====================

@pytest.mark.parametrize("text", [
    "сколько времени",
    "какой сегодня день",
    "сколько памяти занято",
    "что такое фотосинтез",
    "кто такой Ньютон",
    "как работает двигатель",
    "привет",
])
def test_questions_recognised(qa, text):
    """Вопрос уходит за ответом, а не в исполнитель команд."""
    assert qa.is_question(text) is True, f"«{text}» не признан вопросом"


@pytest.mark.parametrize("text", [
    "открой браузер",
    "закрой дискорд",
    "напомни через час позвонить",
    "запусти блокнот",
    "сделай громче",
    "открой папку загрузки",
])
def test_commands_are_not_questions(qa, text):
    """
    Пара к тесту выше — и куда более важная.

    Команда, принятая за вопрос, уходит в LLM: вместо запуска браузера человек
    получает рассказ о том, что такое браузер.
    """
    assert qa.is_question(text) is False, f"«{text}» ошибочно принята за вопрос"


# ==================== Сведения о машине ====================

def test_time_answer_contains_digits(qa):
    """Ответ о времени должен содержать само время."""
    answer = qa.get_current_time(qa.parse_question("сколько времени"))
    assert any(char.isdigit() for char in answer), f"во времени нет цифр: {answer}"


def test_cpu_answer_has_percent(qa):
    """Загрузка процессора — это число с процентом, а не рассуждение."""
    answer = qa.get_cpu_info(qa.parse_question("какая загрузка процессора"))
    assert "%" in answer


def test_ram_answer_mentions_memory(qa):
    """Ответ о памяти называет объём."""
    answer = qa.get_ram_info(qa.parse_question("сколько памяти занято"))
    assert any(unit in answer.lower() for unit in ("гб", "gb", "%"))


def test_russian_question_answered_in_russian(qa):
    """
    Язык ответа берётся из языка вопроса.

    Scott зачитывает ответ вслух русским голосом: английская фраза в нём
    звучит как набор букв.
    """
    question = qa.parse_question("сколько времени")
    assert question.context["language"] == "ru"
    assert qa.parse_question("what time is it").context["language"] == "en"


# ==================== Подробность и приветствия ====================

@pytest.mark.parametrize("text,expected", [
    ("расскажи подробно про космос", "long"),
    ("коротко о космосе", "short"),
    ("что такое космос", "normal"),
])
def test_verbosity_detected(qa, text, expected):
    """
    «Подробнее» и «коротко» — просьба к длине ответа, а не часть темы.

    Без этого Scott зачитывал вслух три абзаца там, где просили одно
    предложение.
    """
    assert qa._detect_verbosity(text) == expected


def test_verbosity_markers_stripped(qa):
    """Указание на длину не должно попадать в тему вопроса."""
    cleaned = qa._strip_verbosity_markers("расскажи подробно про космос")
    assert "подробно" not in cleaned.lower()
    assert "космос" in cleaned.lower()


@pytest.mark.parametrize("text", [
    "привет",
    "Привет!",
    "здравствуй",
    "добрый день",
    "привет, Скотт",
    "добрый день, Скотт!",
])
def test_greetings_answered_locally(qa, text):
    """
    На чистое приветствие Scott отвечает сам.

    Гонять «привет» через LLM — значит ждать секунды там, где ответ известен
    заранее, и тратить лимит запросов. Обращение по имени ничего не меняет:
    «привет, Скотт» — то же приветствие.
    """
    assert qa._get_greeting_response(text) is not None


@pytest.mark.parametrize("text", [
    "Привет Скотт! у тебя появилась новая версия, думаю дальше работать над твоим синтезом речи",
    "привет, что такое фотосинтез",
    "здравствуй, какая сейчас погода",
    "добрый день, расскажи про космос",
    "что такое привет по-английски",
])
def test_greeting_does_not_swallow_the_question(qa, text):
    """
    Приветствие в начале не должно съедать всё остальное.

    Живой случай от пользователя: «Привет Скотт! у тебя появилась новая версия,
    думаю дальше работать над твоим синтезом речи» — в ответ пришло «Привет! Я
    Scott. Чем я могу помочь?», и написанное после первого слова пропало. Со
    стороны это выглядит как заученная фраза вместо ответа.

    Правило было привязано к началу строки ради «привет, Scott», но люди почти
    всегда здороваются прежде, чем спросить, — и срабатывало оно не на
    исключениях, а на обычном разговоре.
    """
    assert qa._get_greeting_response(text) is None, f"«{text[:40]}…» ушло в заготовку"


@pytest.mark.parametrize("text", [
    "как дела",
    "Скотт, как дела?",
    "как ты",
    "что ты умеешь",
    "кто ты",
])
def test_small_talk_answered_locally(qa, text):
    """Разговор ни о чём — и заготовленный ответ на него."""
    assert qa._is_small_talk(text.lower()) is True


@pytest.mark.parametrize("text", [
    "как дела с моим отчётом",
    "что ты умеешь делать с файлами",
    "кто ты по гороскопу",
    "как жизнь в Японии",
])
def test_small_talk_needs_the_whole_phrase(qa, text):
    """
    Пара к тесту выше — тот же дефект этажом ниже.

    Шаблон «как дела» был привязан к началу строки, но не к концу, и «как дела
    с моим отчётом» получало в ответ «У меня всё отлично! А у тебя?».
    """
    assert qa._is_small_talk(text.lower()) is False, f"«{text}» ушло в заготовку"
