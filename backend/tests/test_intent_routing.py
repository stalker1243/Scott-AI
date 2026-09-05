"""
Разделение команд к компьютеру и содержательных вопросов.

Это самая застарелая болезнь проекта: правила, привязанные к голому
существительному, регулярно перехватывали обычные вопросы — «Как устроена
память человека?» отвечало загрузкой RAM, «Что такое команда в спорте?»
уходило в powershell-ветку. Обратная беда не менее живуча: «покажи процессы»
считалось вопросом и уезжало в LLM, который писал статью о диспетчере задач
вместо того, чтобы показать процессы.

Поэтому проверки идут парами: для каждой формулировки-команды есть
похожий по словам вопрос, который командой стать не должен.
"""

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def intent_engine():
    from fast_intent import get_fast_intent_engine

    return get_fast_intent_engine()


# ==================== Команды к компьютеру ====================

@pytest.mark.parametrize("phrase,expected", [
    ("сделай громче", "volume_up"),
    ("громче", "volume_up"),
    ("сделай потише", "volume_down"),
    ("тише", "volume_down"),
    ("прибавь звук", "volume_up"),
    ("убавь громкость", "volume_down"),
    ("увеличь яркость", "brightness_up"),
    ("уменьши яркость", "brightness_down"),
])
def test_hardware_control_recognised(intent_engine, phrase, expected):
    """
    Управление громкостью и яркостью распознаётся как команда.

    Раньше Scott на «сделай громче» отвечал, что не может менять громкость
    устройства, — хотя умеет: /extended/system/volume-up работал всё это время,
    просто фраза до него не доходила.
    """
    intent = intent_engine.detect(phrase)
    assert intent.is_command, f"«{phrase}» не признана командой"
    assert intent.intent_type == "system_command"
    assert intent.main_param == expected


@pytest.mark.parametrize("phrase", [
    "покажи процессы",
    "покажи список процессов",
    "какие процессы запущены",
    "запущенные процессы",
    "открой диспетчер задач",
])
def test_process_list_recognised(intent_engine, phrase):
    """Запрос списка процессов — команда, а не повод рассказать про Windows."""
    intent = intent_engine.detect(phrase)
    assert intent.is_command, f"«{phrase}» не признана командой"
    assert intent.intent_type in ("list_processes", "open_app")


@pytest.mark.parametrize("phrase", [
    "статус системы",
    "загрузка процессора",
    "сколько свободно места на диске",
    "сколько памяти занято",
])
def test_system_info_recognised(intent_engine, phrase):
    """Вопросы о состоянии этой машины обслуживаются локально, без похода в LLM."""
    intent = intent_engine.detect(phrase)
    assert intent.is_command, f"«{phrase}» не признана командой"


# ==================== Написание и запуск программ ====================

@pytest.mark.parametrize("phrase", [
    "напиши программу на C которая выводит Hello, World!",
    "напиши код на питоне который считает факториал",
    "создай скрипт для переименования файлов",
    "сделай программу на C++ с циклом",
])
def test_code_requests_recognised(intent_engine, phrase):
    """Просьба написать код доходит до code_assistant, а не до LLM как вопрос."""
    intent = intent_engine.detect(phrase)
    assert intent.intent_type == "write_code", f"«{phrase}» -> {intent.intent_type}"


@pytest.mark.parametrize("phrase", [
    "запусти программу",
    "запусти код",
    "выполни программу",
    "запусти её",
])
def test_run_code_recognised(intent_engine, phrase):
    """
    «Запусти программу» — про написанное Scott, а не про приложение.

    Без отдельного правила фраза уходила в open_app, и Scott искал в системе
    приложение с названием «программу».
    """
    intent = intent_engine.detect(phrase)
    assert intent.intent_type == "run_code", f"«{phrase}» -> {intent.intent_type}"


@pytest.mark.parametrize("phrase", [
    "сделай программу тренировок на неделю",
    "как написать хорошую программу тренировок",
])
def test_non_code_programs_are_not_code(intent_engine, phrase):
    """
    Пара к тесту выше. «Программа» по-русски значит и расписание тренировок, и
    телепередачи — поэтому слова «напиши программу» мало: нужен ещё признак
    программирования (язык, слово «код», оборот «программу, которая…»).
    """
    intent = intent_engine.detect(phrase)
    assert intent.intent_type != "write_code", f"«{phrase}» ошибочно принята за просьбу о коде"


@pytest.mark.parametrize("phrase", [
    "запусти блокнот",
    "открой калькулятор",
    "запусти игру",
])
def test_app_launch_not_stolen_by_run_code(intent_engine, phrase):
    """
    Пара к предыдущему тесту: правило про запуск программы не должно
    перехватывать обычный запуск приложений — оба начинаются с «запусти».
    """
    intent = intent_engine.detect(phrase)
    assert intent.intent_type == "open_app", f"«{phrase}» -> {intent.intent_type}"


# ==================== Случаи из живого разговора ====================

@pytest.mark.parametrize("phrase,expected_param", [
    ("запустить дельторуна", "дельторуна"),
    ("запусти блокнот", "блокнот"),
    ("открой google chrome", "google chrome"),
    ("включить спотифай", "спотифай"),
])
def test_verb_cut_by_word_boundary(phrase, expected_param):
    """
    Глагол вырезается целиком, а не по первым буквам.

    Взято из лога: на «запустить дельторуна» синоним «запусти» нашёлся внутри
    слова «запустить», и резолвер получил на вход «ть дельторуна».
    """
    try:
        from command_parser import CommandParser
    except ImportError:
        from backend.command_parser import CommandParser

    parsed = CommandParser().parse(phrase)
    assert parsed.main_param == expected_param, f"«{phrase}» -> {parsed.main_param!r}"


@pytest.mark.parametrize("phrase", [
    "напомним мне 18.00, зайти в discord",
    "напомни мне в 18:00 зайти в дискорд",
    "напомните вечером написать другу в телеграм",
])
def test_reminder_wins_over_app_launch(intent_engine, phrase):
    """
    Просьба напомнить не должна запускать названную программу сию секунду.

    Ровно это и случилось в логе: Whisper передал «напомним» вместо
    «напомни», правило не сработало, и Scott открыл Discord вместо
    напоминания на вечер — отрапортовав «Выполнено успешно».
    """
    intent = intent_engine.detect(phrase)
    assert intent.intent_type == "reminder", f"«{phrase}» -> {intent.intent_type}"


# ==================== Вопросы, которые командами быть не должны ====================

@pytest.mark.parametrize("phrase", [
    "как устроена память человека",
    "почему в горах становится тише",
    "покажи процессы фотосинтеза",
    "что такое громкость звука в физике",
    "какие процессы происходят в клетке",
    "как написать хорошую программу тренировок",
    "что такое программа передач",
    "что такое команда в спорте",
    "при какой температуре кипит вода",
    "как зовут президента Франции",
])
def test_questions_stay_questions(intent_engine, phrase):
    """
    Содержательные вопросы не должны превращаться в команды к железу.

    Каждая строка здесь — либо реально случившийся в проекте казус, либо
    ловушка для правил, добавленных ради команд выше: «покажи процессы
    фотосинтеза» отличается от «покажи процессы» одним словом, и якорь конца
    строки в регулярном выражении — единственное, что их разделяет.
    """
    intent = intent_engine.detect(phrase)
    assert not intent.is_command, f"«{phrase}» ошибочно принята за команду ({intent.intent_type})"
