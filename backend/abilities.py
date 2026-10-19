"""
Что Scott умеет — списком, с примерами фраз.

Единственное место, где человек может это узнать, — четыре случайных примера на
главной странице. Из них складывается впечатление, что Scott умеет ровно четыре
вещи. Остальное приходится угадывать, а голосовой помощник, возможности
которого угадывают, используется на десятую часть.

ПОЧЕМУ НЕ ПРОСТО СПИСОК В РАЗМЕТКЕ. Умения зависят от машины: на Linux без
brightnessctl яркость не меняется вовсе, без микрофона не работает голос, без
ключа ИИ Scott не отвечает на вопросы. Список, обещающий то, чего здесь нет, —
хуже отсутствия списка: человек решит, что у него сломалось.

Поэтому каждое умение отвечает, доступно ли оно ЗДЕСЬ, и если нет — почему.

ПРИМЕРЫ ФРАЗ — не украшение. Это единственный способ показать, КАК просить:
По примерам можно выбрать простую команду или точный шаг громкости.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional
import os
import sys
import shutil
from pathlib import Path

# Состояния умения.
READY = "ready"            # работает
UNAVAILABLE = "off"        # на этой машине недоступно


def _звук() -> Optional[str]:
    try:
        from . import os_actions
    except ImportError:
        import os_actions

    if os_actions.volume_command("up") is None:
        return "не нашлось, чем управлять звуком"
    return None


def _яркость() -> Optional[str]:
    try:
        from . import os_actions
    except ImportError:
        import os_actions

    if os_actions.brightness_command("up") is None:
        return "не нашлось, чем управлять яркостью"
    return None


def _питание() -> Optional[str]:
    try:
        from . import os_actions
    except ImportError:
        import os_actions

    if os_actions.power_command("shutdown") is None:
        return "выключение на этой системе недоступно"
    return None


def _окна() -> Optional[str]:
    if sys.platform == 'win32':
        return None
    if not sys.platform.startswith('linux'):
        return 'управление окнами пока доступно в Windows и X11'
    if os.environ.get('WAYLAND_DISPLAY') or os.environ.get('XDG_SESSION_TYPE') == 'wayland':
        return 'Wayland ограничивает общее управление окнами; запуск приложений доступен'
    if not os.environ.get('DISPLAY') or not shutil.which('wmctrl'):
        return 'нужны сеанс X11 и wmctrl'
    return None


def _кнопки() -> Optional[str]:
    if sys.platform != 'win32':
        return 'нажатие кнопок через UI Automation пока доступно в Windows'
    executable = Path(os.environ.get('SystemRoot', r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    return None if executable.is_file() else 'не найден Windows PowerShell для UI Automation'


def _микрофон() -> Optional[str]:
    try:
        import sounddevice  # noqa: F401
    except Exception:
        return "нет библиотеки для записи звука"

    try:
        from . import listener as listener_module
    except ImportError:
        import listener as listener_module

    if not listener_module.list_input_devices():
        return "микрофонов в системе не найдено"
    return None


def _модель() -> Optional[str]:
    try:
        from .intelligent_answerer import get_intelligent_answerer
    except ImportError:
        from intelligent_answerer import get_intelligent_answerer

    отвечающий = get_intelligent_answerer()
    if отвечающий is None or not getattr(отвечающий, "enabled", False):
        return "не настроена модель ИИ — ответы на вопросы недоступны"
    return None

def _точный_звук() -> Optional[str]:
    from system_volume import available
    return None if available() else 'нужен нативный помощник ScottSystem или системный инструмент звука'


# Умения, сгруппированные по тому, к чему они относятся.
#
# Порядок не случаен: сверху то, ради чего помощника заводят, — открыть
# программу и спросить. Выключение компьютера стоит последним: оно нужно реже
# всего, а выглядит внушительнее всего.
ABILITIES: List[Dict] = [
    {
        'group': 'Локальные инструменты',
        'items': [
            {'id': 'calculate', 'title': 'Вычисления', 'detail': 'Арифметика, проценты, корень и округление без модели ИИ',
             'examples': ['посчитай (12 + 3) / 5', 'сколько будет 15 процентов от 200', 'вычисли корень из 144']},
            {'id': 'convert_units', 'title': 'Перевод единиц', 'detail': 'Длина, масса, время, площадь, объём, скорость, данные и температура',
             'examples': ['переведи 2.5 километра в метры', 'переведи 32 фаренгейта в цельсия', 'переведи 1 гибибайт в мегабайты']},
            {'id': 'calendar_tools', 'title': 'Даты и дни', 'detail': 'Дата, день недели, дни до события или между двумя датами',
             'examples': ['какой завтра день недели', 'сколько дней до 31.12.2026', 'сколько дней между 01.01.2026 и 31.12.2026']},
            {'id': 'stopwatch', 'title': 'Секундомер', 'detail': 'Запуск, пауза, продолжение, круги и сброс; до перезапуска backend',
             'examples': ['запусти секундомер', 'поставь секундомер на паузу', 'продолжи секундомер', 'засеки круг', 'сколько на секундомере', 'останови секундомер', 'сбрось секундомер']},
            {'id': 'random_tools', 'title': 'Случайный выбор', 'detail': 'Число в заданном диапазоне, кубик и монета',
             'examples': ['случайное число от 1 до 100', 'брось кубик', 'подбрось монету']},
            {'id': 'system_volume_exact', 'title': 'Точная громкость системы', 'detail': 'Уровень 0–100%, изменение на шаг, mute и проверка состояния',
             'examples': ['установи системную громкость на 30 процентов', 'увеличь громкость системы на десять процентов', 'выключи системный звук', 'покажи системную громкость'],
             'check': _точный_звук},
        ],
    },
    {
        "group": "Программы и файлы",
        "items": [
            {
                "id": "open_app",
                "title": "Открыть программу",
                "detail": "Любую установленную — Scott находит её сам, по названию из меню",
                "examples": ["открой браузер", "запусти блокнот", "открой дискорд"],
            },
            {
                "id": "close_app",
                "title": "Закрыть программу",
                "detail": "По названию или по тому, что написано в заголовке окна",
                "examples": ["закрой дискорд", "заверши процесс chrome"],
            },
            {
                "id": "desktop_windows",
                "title": "Управлять окнами",
                "detail": "Показать окна, переключиться, свернуть, развернуть или запросить закрытие с сохранением документов",
                "examples": ["покажи открытые окна", "закрой все окна кроме Firefox", "сверни окно Telegram", "переключись на Spotify"],
                "check": _окна,
            },
            {
                "id": "desktop_controls",
                "title": "Нажать кнопку приложения",
                "detail": "По доступному названию кнопки, если приложение предоставляет интерфейс автоматизации",
                "examples": ["покажи кнопки в Spotify", "нажми кнопку «Воспроизвести» в Spotify"],
                "check": _кнопки,
            },
            {
                "id": "app_catalog",
                "title": "Каталог приложений",
                "detail": "Находит установленные приложения по системному каталогу без отдельной настройки команд",
                "examples": ["покажи установленные программы", "обнови список приложений"],
            },
            {
                "id": "folders",
                "title": "Открыть папку",
                "detail": "Загрузки, документы, рабочий стол",
                "examples": ["открой загрузки", "открой рабочий стол"],
            },
            {
                "id": "projects",
                "title": "Открыть проект",
                "detail": "Папку проекта — по названию, которое вы ему дали в разделе «Проекты»",
                # С названием, а не просто «открой проект»: без него Scott
                # честно ответит «не сказано какой», и пример научил бы
                # человека фразе, которая не работает.
                "examples": ["открой проект ScottAI"],
            },
        ],
    },
    {
        "group": "Разговор",
        "items": [
            {
                "id": "ask",
                "title": "Ответить на вопрос",
                "detail": "Объяснить, посчитать, перевести, подсказать по работе",
                "examples": ["что такое фотосинтез", "чем отличается http от https"],
                "check": _модель,
            },
            {
                "id": "remember",
                "title": "Запомнить о вас",
                "detail": "Сказанное однажды Scott учитывает в каждом следующем ответе",
                "examples": ["запомни, что я работаю в вечернюю смену"],
            },
            {
                "id": "speech_settings",
                "title": "Настроить озвучку",
                "detail": "Выбор голоса, его громкость и тихий режим",
                "examples": ["выбери голос Светланы", "громкость голоса пятьдесят процентов", "покажи голоса", "выключи озвучку"],
            },
            {
                "id": "voice",
                "title": "Слышать по имени",
                "detail": "Микрофон открыт постоянно, но выполняется только сказанное после имени",
                "examples": ["Скотт, сколько времени"],
                "check": _микрофон,
            },
        ],
    },
    {
        "group": "Компьютер",
        "items": [
            {
                "id": "volume",
                "title": "Громкость",
                "detail": "Прибавить или убавить звук системы",
                "examples": ["сделай громче", "убавь звук"],
                "check": _звук,
            },
            {
                "id": "brightness",
                "title": "Яркость",
                "detail": "Экран ноутбука светлее или темнее",
                "examples": ["сделай ярче", "убавь яркость"],
                "check": _яркость,
            },
            {
                "id": "system",
                "title": "Состояние машины",
                "detail": "Загрузка процессора, памяти, места на диске, список процессов",
                "examples": ["сколько места на диске", "покажи процессы"],
            },
            {
                "id": "power",
                "title": "Выключение и перезагрузка",
                "detail": "С задержкой, чтобы успеть передумать",
                "examples": ["выключи компьютер", "перезагрузи компьютер"],
                "check": _питание,
            },
        ],
    },
    {
        "group": "Интернет",
        "items": [
            {
                "id": "search",
                "title": "Найти в сети",
                "detail": "Поиск в браузере по вашему запросу",
                "examples": ["найди рецепт борща", "введи в поиск браузера погоду"],
            },
            {
                "id": "sites",
                "title": "Открыть сайт",
                "detail": "Знакомые сайты — по названию, остальные — по адресу",
                "examples": ["зайди на гитхаб", "открой youtube"],
            },
        ],
    },
    {
        "group": "Время и порядок",
        "items": [
            {
                "id": "reminders",
                "title": "Напомнить",
                "detail": "Через час, в шесть вечера, завтра утром",
                "examples": ["напомни через час позвонить маме", "напомни в 18:00 про встречу"],
            },
            {
                "id": "protocols",
                "title": "Протоколы",
                "detail": "Несколько действий одной фразой — их вы составляете сами",
                "examples": ["протокол рабочий день"],
            },
        ],
    },
]


def describe() -> Dict:
    """
    Умения вместе с тем, доступны ли они на этой машине.

    Проверка каждого обёрнута: упавшая не должна уносить весь список — человек
    остался бы вовсе без ответа на вопрос «что ты умеешь».
    """
    группы = []

    for группа in ABILITIES:
        пункты = []

        for умение in группа["items"]:
            проверка: Optional[Callable] = умение.get("check")
            причина = None

            if проверка is not None:
                try:
                    причина = проверка()
                except Exception as e:
                    причина = f"проверить не удалось: {e}"

            пункты.append({
                "id": умение["id"],
                "title": умение["title"],
                "detail": умение["detail"],
                "examples": умение["examples"],
                "state": UNAVAILABLE if причина else READY,
                "reason": причина or "",
            })

        группы.append({"group": группа["group"], "items": пункты})

    доступно = sum(1 for г in группы for п in г["items"] if п["state"] == READY)
    всего = sum(len(г["items"]) for г in группы)

    return {"groups": группы, "ready": доступно, "total": всего}
