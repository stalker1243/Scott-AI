"""
Что значит сказанное: одно место вместо трёх.

До сих пор смысл фразы определяли три модуля независимо друг от друга:

* `fast_intent` — по регулярным выражениям с якорями;
* `command_parser` — по очкам за совпадение синонимов;
* `question_answerer.is_question` — вопрос это или команда.

Каждый из них знал свой набор слов, и наборы пересекались. Мирил их `main.py`
полудюжиной заплаток вида «если парсер не понял, беру тип из намерения» —
каждая появилась после того, как очередная фраза уехала не туда. Из-за этого
правка в одном месте неслышно меняла поведение в другом: так «закрой дискорд»
стало запускать дискорд, а «привет, что такое фотосинтез» — отвечать
заготовкой.

Здесь решение принимается один раз и целиком. Модуль ничего не делает — только
решает и объясняет, почему решил так: `Decision.reason` попадает и в лог, и в
снимок маршрутизации, по которому видно, что фраза поехала не туда.

Исполнение осталось в `main.py`: разделение решения и последствий — главное,
что даёт этот модуль. Решение можно проверить полсотней фраз за три секунды,
не запуская ни одной программы и не выходя в сеть.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

import vocabulary

# ==================== Что может быть решено ====================


@dataclass
class Decision:
    """
    Итог разбора: что Scott собирается сделать с этой фразой.

    `reason` — не украшение. Когда фраза уезжает не туда, первый вопрос
    «почему», и ответ на него должен быть в логе, а не в голове того, кто
    писал код.
    """

    kind: str                       # 'web' | 'question' | 'action' | 'refused'
    reason: str = ""

    # kind='web'
    service: str = ""               # youtube | github
    query: str = ""                 # что искать; пусто — открыть сам сайт

    # kind='action'
    action: str = ""                # тип команды
    param: str = ""

    # kind='refused'
    message: str = ""

    # Исходники разбора: исполнителю нужен `parsed`, логам — оба.
    parsed: Any = None
    intent: Any = None


# ==================== Слова ====================

# Служебные слова веб-запросов: имя сервиса, глаголы-триггеры. После их
# вырезания остаётся то, что человек действительно просил найти.
YOUTUBE_FILLER_WORDS = {
    'скотт', 'scott', 'ютуб', 'ютубе', 'ютубу', 'youtube', 'найди', 'найти',
    'включи', 'включить', 'открой', 'открыть', 'запусти', 'запустить',
    'поищи', 'искать', 'поиск', 'видео', 'ролик', 'про', 'на', 'в', 'из', 'и',
}

GITHUB_FILLER_WORDS = {
    'скотт', 'scott', 'гитхаб', 'гитхабе', 'github', 'зайди', 'зайти',
    'открой', 'открыть', 'найди', 'найти', 'выбери', 'выбрать', 'поищи',
    'поиск', 'репозиторий', 'репозиторию', 'репо', 'этот', 'эту', 'это',
    'на', 'в', 'и',
}

# Слова, которыми человек уточняет «просто открой сайт»: после их вырезания
# запрос оказывается пустым, и Scott открывает главную вместо поиска. В логе
# была фраза «открой youtube в главное меню» — Scott искал на YouTube «главное
# меню».
SITE_WORDS = set(vocabulary.SITE_WORDS)

# По каким сервисам Scott умеет искать, и по каким словам они узнаются.
WEB_SERVICES = (
    ('youtube', ('ютуб', 'youtube'), YOUTUBE_FILLER_WORDS),
    ('github', ('гитхаб', 'github'), GITHUB_FILLER_WORDS),
)

# Приставки, по которым видно приказ, а не разговор. Выводятся из общих
# глаголов запуска: держать их отдельным списком значило бы забыть про
# вежливое «откройте», как это уже случалось.
EXPLICIT_ACTION_PREFIXES = tuple(verb + ' ' for verb in vocabulary.LAUNCH_VERBS) + (
    'вкл ', 'open file ', 'открой файл ',
)

# Названия, при упоминании которых речь почти наверняка о программе.
KNOWN_APP_NAMES = vocabulary.KNOWN_APP_NAMES

# Человек прямо просит поискать, а не отвечать самому.
EXPLICIT_SEARCH_WORDS = vocabulary.SEARCH_WORDS

# Типы, которые Scott выполняет сам.
ACTION_COMMAND_TYPES = {
    'open_app', 'close_app', 'create_file', 'create_folder', 'open_website',
    'get_currency', 'get_weather', 'get_news', 'system_info', 'manage_window',
    'file_operation', 'system_command', 'open_url',
    'list_processes', 'open_folder', 'reminder', 'write_code', 'run_code',
}

# Оболочка — никогда через общий путь.
#
# `/command` не требует токена, и стоит появиться здесь ветке выполнения, как
# произвольная команда оболочки станет доступна любому, кто дотянулся до
# порта. Выполнять их можно только через `/extended/powershell` и
# `/internal/execute`: там есть и Bearer-токен, и ограничитель частоты, и
# белый список.
SHELL_TYPES = {'powershell', 'run_script'}

SHELL_REFUSAL = (
    "Выполнять команды оболочки голосом я не буду — это делается "
    "через защищённый эндпоинт с токеном."
)

# Намерения, которым доверяем больше, чем разбору по очкам. Каждое попало сюда
# после того, как разбор ошибся именно на нём.
INTENT_WINS_WHEN_PARSER_LOST = (
    'system_command', 'list_processes', 'open_folder',
    'reminder', 'write_code', 'run_code',
)

# Намерения, которые сильнее разбора всегда, а не только при его провале.
INTENT_ALWAYS_WINS = ('reminder', 'write_code', 'run_code')

QUESTION_KEYWORDS = vocabulary.QUESTION_WORDS


# ==================== Само решение ====================


def understand(text: str, *, intent_engine, parser, answerer) -> Decision:
    """
    Решить, что значит фраза.

    Движки передаются снаружи, а не берутся из `main`: так решение можно
    проверить, не поднимая backend целиком, и порядок загрузки модулей ни на
    что не влияет.
    """
    lower = text.lower().strip()
    intent = intent_engine.detect(text)

    # 1. Названный сервис — самый надёжный признак из всех. Упоминание YouTube
    #    или GitHub однозначно говорит о намерении, и рисковать тем, что общая
    #    логика «вопрос или команда» переклассифицирует фразу, незачем: на
    #    пересечении их словарей уже не раз ловились ошибки.
    for service, markers, filler in WEB_SERVICES:
        if any(marker in lower for marker in markers):
            query = extract_web_query(text, filler | SITE_WORDS)
            return Decision(
                kind='web',
                service=service,
                query=query,
                reason=f"назван {service}" + (f", искать «{query}»" if query else ", открыть сайт"),
                intent=intent,
            )

    # 2. Вопрос — если это не явный приказ. Порядок важен: «Можешь открыть
    #    блокнот?» оформлено вопросом, но is_command об этом знает.
    if not intent.is_command and answerer.is_question(text):
        return Decision(kind='question', reason="вопрос по форме", intent=intent)

    # 3. Разбор команды. Если намерение уверено, что это приказ, сначала
    #    снимаем вежливую обёртку: разборщик заметно надёжнее на чистом
    #    императиве («открой блокнот»), чем на «Скотт, можешь открыть блокнот?».
    command_text = strip_command_wrapper(text) if intent.is_command else text
    parsed = parser.parse(command_text)
    notes = []

    if parsed.command_type == 'unknown' and intent.intent_type in INTENT_WINS_WHEN_PARSER_LOST:
        # Разборщик не знает формулировок вроде «сделай громче» и возвращает
        # на них unknown, а решение принимается по нему — команда молча
        # превращалась в вопрос к ИИ.
        parsed.command_type = intent.intent_type
        parsed.main_param = intent.main_param
        notes.append(f"разбор не понял, тип из намерения ({intent.intent_type})")

    if intent.intent_type == 'open_folder' and parsed.command_type in ('open_app', 'unknown'):
        # Разборщик видит глагол «открой» и считает «открой загрузки» запуском
        # программы. Намерение разобралось, что речь о папке.
        parsed.command_type = 'open_folder'
        parsed.main_param = intent.main_param
        notes.append("папка, а не программа")

    if intent.intent_type in INTENT_ALWAYS_WINS:
        # «Напомни через час открыть почту»: разборщик видит «открыть почту» и
        # предлагает сделать это сейчас — то есть ровно не то, о чём просили.
        # То же с «напиши программу на C»: там видят «программу» и пытаются её
        # запустить.
        parsed.command_type = intent.intent_type
        parsed.main_param = intent.main_param
        notes.append(f"намерение сильнее разбора ({intent.intent_type})")

    explicit_search = any(word in lower for word in EXPLICIT_SEARCH_WORDS)

    # 4. Поиск без просьбы искать — обычно всё-таки вопрос: «что такое яндекс»
    #    не значит «поищи в яндексе».
    if parsed.command_type == 'search' and not explicit_search and looks_like_question(text, intent):
        return Decision(
            kind='question',
            reason="разобрано как поиск, но по форме это вопрос",
            parsed=parsed,
            intent=intent,
        )

    # 5. Оболочку не выполняем никогда — проверка стоит раньше исполнения.
    if parsed.command_type in SHELL_TYPES:
        return Decision(
            kind='refused',
            reason=f"команда оболочки «{parsed.command_type}» через общий путь",
            message=SHELL_REFUSAL,
            parsed=parsed,
            intent=intent,
        )

    # 6. Выполнять или всё-таки отвечать.
    explicit_action = any(lower.startswith(prefix) for prefix in EXPLICIT_ACTION_PREFIXES)
    explicit_app = any(name in lower for name in KNOWN_APP_NAMES)

    should_act = (
        parsed.command_type in ACTION_COMMAND_TYPES
        or (parsed.command_type == 'search' and explicit_search)
        or explicit_action
        or explicit_app
    )

    if should_act:
        return Decision(
            kind='action',
            action=parsed.command_type,
            param=parsed.main_param,
            reason="; ".join(notes) or _why_act(parsed, explicit_action, explicit_app, explicit_search),
            parsed=parsed,
            intent=intent,
        )

    # 7. Ни вопрос по форме, ни знакомая команда. Короткая фраза скорее
    #    разговор, чем приказ, — на такие лучше ответить, чем сделать
    #    неизвестно что.
    if answerer.is_question(text) or len(lower.split()) <= 5:
        return Decision(
            kind='question',
            reason="не похоже на команду" + (" (короткая фраза)" if len(lower.split()) <= 5 else ""),
            parsed=parsed,
            intent=intent,
        )

    # 8. Последняя возможность: выполнить то, что разобралось.
    return Decision(
        kind='action',
        action=parsed.command_type,
        param=parsed.main_param,
        reason="ни вопрос, ни разговор — пробую выполнить",
        parsed=parsed,
        intent=intent,
    )


def _why_act(parsed, explicit_action: bool, explicit_app: bool, explicit_search: bool) -> str:
    """Короткое объяснение, почему фраза признана приказом."""
    if parsed.command_type in ACTION_COMMAND_TYPES:
        return f"известное действие ({parsed.command_type})"
    if explicit_search:
        return "явная просьба поискать"
    if explicit_action:
        return "начинается с приказа"
    if explicit_app:
        return "названа знакомая программа"
    return "разобрано как действие"


# ==================== Разбор текста ====================


def strip_command_wrapper(text: str) -> str:
    """
    Убрать вежливую и вопросительную обёртку вокруг явного приказа.

    «Скотт, можешь открыть блокнот?» → «открыть блокнот». Без этого разборщик
    не узнаёт команду и уходит в ИИ с ответом «у меня нет доступа к ОС».
    """
    t = text.strip()
    if t.endswith('?'):
        t = t[:-1].strip()

    name_prefixes = ('скотт,', 'скотт ', 'scott,', 'scott ')
    lower_t = t.lower()
    for name in name_prefixes:
        if lower_t.startswith(name):
            t = t[len(name):].strip()
            lower_t = t.lower()
            break

    changed = True
    while changed:
        changed = False
        for w in vocabulary.POLITE_WRAPPERS:
            if lower_t.startswith(w):
                t = t[len(w):].strip()
                lower_t = t.lower()
                changed = True

    return t or text.strip()


def extract_web_query(text: str, filler_words) -> str:
    """
    Оставить от фразы только то, что нужно искать.

    «Скотт, найди на ютубе видео про запуск ракеты» → «запуск ракеты». Свой
    список служебных слов, а не общий словарь синонимов разборщика: тот уже не
    раз ломался на пересечении категорий.
    """
    words = strip_command_wrapper(text).split()
    kept = [w for w in words if w.lower().strip('.,!?:;—-') not in filler_words]
    return ' '.join(kept).strip()


def looks_like_question(text: str, intent=None) -> bool:
    """
    Похожа ли фраза на вопрос по форме.

    Раньше сюда передавали объект намерения, а обращались как со строкой:
    `intent.lower()`. Любая фраза, дошедшая до этой проверки, роняла обработку
    с «'IntentResult' object has no attribute 'lower'» — и человек видел
    «❌ Ошибка» вместо ответа. Сбой был незаметен ровно потому, что дойти сюда
    удавалось редко: нужен был разбор в «поиск» без явной просьбы искать.
    """
    if text.strip().endswith('?'):
        return True

    if intent is not None:
        if getattr(intent, 'is_question', False):
            return True
        if getattr(intent, 'intent_type', '') == 'question':
            return True

    lower = text.lower()
    return any(
        re.search(rf'\b{re.escape(keyword)}\b', lower)
        for keyword in QUESTION_KEYWORDS
    )
