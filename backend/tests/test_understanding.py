"""
Разбор фразы: одно решение вместо трёх спорящих.

До сведения смысл сказанного определяли три модуля независимо — `fast_intent`,
`command_parser` и `question_answerer.is_question`, — а `main.py` мирил их
полудюжиной заплаток. Проверить решение было почти невозможно: чтобы узнать,
что Scott сделает с фразой, приходилось поднимать backend целиком и следить,
не полез ли он в сеть.

Теперь решение отделено от последствий, и его можно спросить напрямую. Здесь
проверяется именно оно: куда уходит фраза и почему, — без запуска программ,
без файлов на диске и без единого обращения к сети.
"""

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def движки():
    """Настоящие движки разбора: подменять их здесь нечем и незачем."""
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

    return understanding, {
        "intent_engine": get_fast_intent_engine(),
        "parser": CommandParser(),
        "answerer": get_question_answerer(),
    }


@pytest.fixture
def решить(движки):
    understanding, engines = движки
    return lambda text: understanding.understand(text, **engines)


# ==================== Действия ====================

@pytest.mark.parametrize("phrase,action", [
    ("открой браузер", "open_app"),
    ("закрой дискорд", "close_app"),
    ("выключи музыку", "close_app"),
    ("создай папку отчёты", "create_folder"),
    ("сделай громче", "system_command"),
    ("напомни через час позвонить маме", "reminder"),
    ("покажи процессы", "list_processes"),
    ("открой папку загрузки", "open_folder"),
])
def test_actions_recognised(решить, phrase, action):
    """Приказ опознаётся как приказ, и притом верный."""
    decision = решить(phrase)
    assert decision.kind == "action", f"«{phrase}» -> {decision.kind}"
    assert decision.action == action, f"«{phrase}» -> {decision.action}"


# ==================== Вопросы ====================

@pytest.mark.parametrize("phrase", [
    "сколько времени",
    "что такое фотосинтез",
    "почему небо голубое",
    "привет",
    "как дела",
    "как устроена память человека",
    "при какой температуре кипит вода",
    "что такое команда в спорте",
    "создай программу занятий для новичка",
    "напиши письмо начальнику",
])
def test_questions_recognised(решить, phrase):
    """
    Вопрос уходит за ответом, а не в исполнитель.

    Последние две строки — просьбы что-то сочинить. Долго они означали пустой
    файл с таким именем и бодрый отчёт «Всё сделано».
    """
    assert решить(phrase).kind == "question", f"«{phrase}» -> {решить(phrase).kind}"


# ==================== Сайты ====================

@pytest.mark.parametrize("phrase,query", [
    ("открой ютуб", ""),
    ("зайди на ютуб", ""),
    ("открой youtube", ""),
    ("найди на ютубе рецепт борща", "рецепт борща"),
])
def test_youtube(решить, phrase, query):
    """
    Названный сервис — самый надёжный признак из всех.

    Пустой запрос означает «открой сам сайт»: «зайди на ютуб» долго искало на
    YouTube слово «зайди», потому что глагол перехода был в списке GitHub, а у
    YouTube его забыли.
    """
    decision = решить(phrase)
    assert decision.kind == "web"
    assert decision.service == "youtube"
    assert decision.query == query, f"«{phrase}» -> {decision.query!r}"


# ==================== Оболочка ====================

def test_shell_is_refused(решить):
    """
    Команды оболочки через общий путь не выполняются никогда.

    `/command` не требует токена, и появись здесь ветка выполнения —
    произвольная команда оболочки стала бы доступна любому, кто дотянулся до
    порта.
    """
    decision = решить("выполни powershell команду")
    assert decision.kind == "refused"
    assert decision.message


# ==================== Решение объясняет себя ====================

def test_decision_explains_itself(решить):
    """
    У каждого решения есть причина, и она читаема.

    Когда фраза уезжает не туда, первый вопрос — «почему», и ответ должен быть
    в логе, а не в голове того, кто писал код.
    """
    for phrase in ("открой браузер", "что такое фотосинтез", "открой ютуб"):
        assert решить(phrase).reason, f"«{phrase}» решено без объяснения"


# ==================== Сбой, который был незаметен ====================

def test_search_without_explicit_request_does_not_crash(решить):
    """
    Разбор в «поиск» без явной просьбы искать не должен ронять обработку.

    `_is_question_like` принимал объект намерения за строку и вызывал у него
    `.lower()`. Любая фраза, дошедшая до этой проверки, падала с
    «'IntentResult' object has no attribute 'lower'», и человек видел
    «❌ Ошибка» вместо ответа.

    Сбой прятался годами ровно потому, что дойти туда удавалось редко: слово
    «yandex» знал разборщик, но список явного поиска о нём не знал.
    """
    decision = решить("yandex котики")
    assert decision.kind in ("action", "question")
    assert decision.action != "" or decision.kind == "question"


def test_looks_like_question_handles_intent_object(движки):
    """
    Проверка формы вопроса принимает объект намерения, а не строку.

    Пара к тесту выше — на том самом месте, где ломалось.
    """
    understanding, engines = движки
    detect = engines["intent_engine"].detect

    вопрос = "что такое фотосинтез"
    приказ = "открой блокнот"

    assert understanding.looks_like_question(вопрос, detect(вопрос)) is True
    assert understanding.looks_like_question(приказ, detect(приказ)) is False

    # Без намерения решает сама форма фразы: вопросительный знак и слова
    # вроде «сколько», «почему».
    assert understanding.looks_like_question("это точно?", None) is True
    assert understanding.looks_like_question("открой блокнот", None) is False


# ==================== Вежливость вокруг приказа ====================

@pytest.mark.parametrize("phrase,expected", [
    ("Скотт, можешь открыть блокнот?", "открыть блокнот"),
    ("пожалуйста открой хром", "открой хром"),
    ("не мог бы ты запустить телеграм", "запустить телеграм"),
])
def test_wrapper_stripped(движки, phrase, expected):
    """
    Вежливая обёртка снимается перед разбором.

    Разборщик заметно надёжнее на чистом императиве: без этого «Скотт, можешь
    открыть блокнот?» уходило в ИИ с ответом «у меня нет доступа к ОС».
    """
    understanding, _ = движки
    assert understanding.strip_command_wrapper(phrase).lower() == expected


# ==================== Списки слов не разъезжаются ====================

def test_search_words_cover_the_parser(движки):
    """
    Все слова поиска, известные разборщику, должны считаться явным поиском.

    Расхождение этих двух списков и открыло путь к сбою: «yandex» знал
    разборщик, а список явного поиска — нет.
    """
    understanding, engines = движки
    parser_words = engines["parser"].COMMAND_SYNONYMS["search"]

    забытые = [
        word for word in parser_words
        if not any(known in word for known in understanding.EXPLICIT_SEARCH_WORDS)
    ]
    assert not забытые, f"разборщик знает слова поиска, а список явного — нет: {забытые}"


# ==================== Вопрос сильнее глагола ====================

@pytest.mark.parametrize("phrase", [
    "чем открыть pdf",
    "как открыть архив zip",
    "где открыть счёт в банке",
    "сколько можно открыть вкладок",
    "Скотт, чем открыть djvu",
    "чем выключить компьютер по расписанию",
])
def test_question_word_beats_verb(решить, phrase):
    """
    Вопросительное слово в начале сильнее глагола в середине.

    «Чем открыть pdf» — вопрос о том, какой программой это делается. Scott же
    пытался запустить программу с названием «чем pdf» и рапортовал о неудаче.
    Глагол «открыть» встречался в фразе, движок намерений объявлял её приказом,
    и проверка «вопрос ли это» не выполнялась вовсе: она стоит под условием
    «если не приказ».
    """
    decision = решить(phrase)
    assert decision.kind == "question", f"«{phrase}» -> {decision.kind}/{decision.action}"


@pytest.mark.parametrize("phrase,action", [
    ("какая погода", "get_weather"),
    ("какие процессы запущены", "list_processes"),
])
def test_question_word_does_not_break_real_commands(решить, phrase, action):
    """
    Пара к тесту выше, и она важнее.

    Многие настоящие команды начинаются с вопросительного слова: «какая
    погода», «какие процессы запущены». Правило нарочно узкое — оно перебивает
    только действия с программами и файлами, где «чем открыть» означает
    просьбу посоветовать.
    """
    decision = решить(phrase)
    assert decision.kind == "action", f"«{phrase}» -> {decision.kind}"
    assert decision.action == action


@pytest.mark.parametrize("phrase", [
    "открой блокнот",
    "закрой дискорд",
    "можешь открыть телеграм",
    "открой папку загрузки",
])
def test_plain_commands_unaffected(решить, phrase):
    """Приказы без вопросительного слова остались приказами."""
    assert решить(phrase).kind == "action", f"«{phrase}» -> {решить(phrase).kind}"
