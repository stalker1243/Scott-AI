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


# ==================== Вопросы, которые командами быть не должны ====================

@pytest.mark.parametrize("phrase", [
    "как устроена память человека",
    "почему в горах становится тише",
    "покажи процессы фотосинтеза",
    "что такое громкость звука в физике",
    "какие процессы происходят в клетке",
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
