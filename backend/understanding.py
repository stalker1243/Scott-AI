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
import voice_commands
from command_parser import ParsedCommand

# ==================== Что может быть решено ====================


@dataclass
class Decision:
    """
    Итог разбора: что Scott собирается сделать с этой фразой.

    `reason` — не украшение. Когда фраза уезжает не туда, первый вопрос
    «почему», и ответ на него должен быть в логе, а не в голове того, кто
    писал код.
    """

    kind: str                       # 'protocol' | 'web' | 'question' | 'action' | 'remember' | 'project' | 'schedule' | 'refused'
    reason: str = ""

    # kind='protocol'
    protocol: Any = None            # сам протокол, найденный по фразе

    # kind='web'
    service: str = ""               # youtube | github
    query: str = ""                 # что искать; пусто — открыть сам сайт

    # kind='action'
    action: str = ""                # тип команды
    param: str = ""

    # kind='remember'
    memory: str = ""            # что именно запомнить

    # kind='project'
    project: str = ""           # название проекта, который просят открыть

    # kind='schedule'
    when: Any = None            # когда выполнить
    order: str = ""             # что именно выполнить

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

# Действия с программами и файлами.
#
# Отдельный список нужен ради одного правила: вопросительное слово в начале
# фразы перебивает эти типы, но не остальные. «Чем открыть pdf» — просьба
# посоветовать, а не запустить программу «чем pdf»; зато «какая погода» и
# «сколько памяти занято» тоже начинаются с вопросительного слова, и это
# настоящие команды, на которые Scott отвечает сам.
PROGRAM_ACTION_TYPES = {
    'open_app', 'close_app', 'create_file', 'create_folder',
    'open_folder', 'open_website', 'open_url',
    'manage_window', 'file_operation',
    # Управление машиной здесь же, и по той же причине: «чем выключить
    # компьютер по расписанию» — просьба посоветовать, а не выключить.
    'system_command',
}

# Типы, которые Scott выполняет сам.
ACTION_COMMAND_TYPES = {
    'open_app', 'close_app', 'create_file', 'create_folder', 'open_website',
    'get_currency', 'get_weather', 'get_news', 'system_info', 'manage_window',
    'file_operation', 'system_command', 'open_url',
    'list_processes', 'open_folder', 'reminder', 'write_code', 'run_code', 'voice_settings',
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

# Массовое удаление голосом.
#
# «Удали все файлы с рабочего стола» разбор не понимал вовсе и возвращал
# unknown — фраза уходила в модель, и та отвечала рассуждением об удалении
# файлов. Выполнено бы оно не было (путь из такой фразы не определяется), но
# молчаливое непонимание здесь — худший исход: человек не знает, сделано или
# нет, и повторяет.
#
# Отказываем прямо. Удалить один названный файл Scott умеет и через голос —
# речь только о том, что нельзя отменить одним движением.
# Глагол берётся по основе, а не точной формой: проверка слухом показала, что
# Whisper слышит «очисти» как «очистив», и точное совпадение перестаёт
# работать — фраза уходит в модель вместо отказа.
MASS_DELETE = re.compile(
    r"\b(?:удал\w*|сотр\w*|стер\w*|очист\w*)\s+"
    r"(?:все|всё|весь|всю)\b",
    re.IGNORECASE,
)

MASS_DELETE_REFUSAL = (
    "Удалять всё разом голосом я не стану: отменить это будет нельзя. "
    "Назовите файл, который нужно удалить, или сделайте это в проводнике."
)

# Намерения, которым доверяем больше, чем разбору по очкам. Каждое попало сюда
# после того, как разбор ошибся именно на нём.
INTENT_WINS_WHEN_PARSER_LOST = (
    'system_command', 'list_processes', 'open_folder',
    'reminder', 'write_code', 'run_code',
    # Закрытие программы добавлено после проверки слухом: Whisper расслышал
    # «выключи музыку» как «выключим музыку», разборщик такой формы не знает и
    # вернул unknown — фраза уходила в модель. Намерение при этом было верным.
    'close_app',
)

# То, на что Scott отвечает сам, глядя на машину.
#
# Эти фразы по форме вопросы — «сколько места на диске», «как загружен
# процессор», «какие процессы запущены», — и проверка «вопрос ли это» уводила
# их в модель. Та отвечала статьёй о том, как посмотреть место на диске, вместо
# того чтобы его посмотреть: она и не может знать, сколько его здесь.
#
# Проверяется раньше вопроса именно поэтому: вопрос о состоянии этой машины —
# не вопрос к модели, а команда посмотреть.
SELF_ANSWERABLE = {'system_info', 'list_processes'}

# Намерения, которые сильнее разбора всегда, а не только при его провале.
INTENT_ALWAYS_WINS = ('reminder', 'write_code', 'run_code')

# Что умеет системная команда — ровно то, что различает исполнитель.
#
# Список нужен, чтобы понять, разобралось ли намерение до конца. «Убавь
# яркость» разборщик тоже считает системной командой, но кладёт в параметр
# слово «убавь» — а исполнитель ждёт brightness_down и не находит его.
SYSTEM_ACTIONS = {
    'volume_up', 'volume_down', 'brightness_up', 'brightness_down',
    'sleep', 'restart', 'shutdown',
}

QUESTION_KEYWORDS = vocabulary.QUESTION_WORDS


# ==================== Само решение ====================


def understand(text: str, *, intent_engine, parser, answerer,
               find_protocol=None) -> Decision:
    """
    Решить, что значит фраза.

    Движки передаются снаружи, а не берутся из `main`: так решение можно
    проверить, не поднимая backend целиком, и порядок загрузки модулей ни на
    что не влияет. По той же причине протокол ищется переданной функцией, а не
    импортом: модуль решений не должен знать, где лежат протоколы.
    """
    lower = text.lower().strip()
    intent = intent_engine.detect(text)

    # 0. Протокол человек составил сам и назвал сам. Что бы ни думали о фразе
    #    встроенные правила, его собственная настройка сильнее: иначе
    #    протокол, названный обычными словами, было бы невозможно позвать.
    #
    #    Перехватывать чужие фразы он при этом не может — совпадение имени
    #    только точное, см. ProtocolStore.match.
    if find_protocol is not None:
        protocol = find_protocol(text)
        if protocol is not None:
            return Decision(
                kind='protocol',
                protocol=protocol,
                reason=f"позван протокол «{getattr(protocol, 'name', '')}»",
                intent=intent,
            )

    voice_command = voice_commands.parse(strip_command_wrapper(text))
    if voice_command is not None:
        parsed = ParsedCommand('voice_settings', voice_command.action,
                               {'voice_value': voice_command.value}, 1.0)
        return Decision(kind='action', action='voice_settings', param=voice_command.action,
                        parsed=parsed, intent=intent, reason='настройка озвучки Scott')

    # 0.5 Просьба запомнить.
    #
    #     Стоит до всего остального, потому что «запомни, что я работаю в
    #     вечернюю смену» по всем прочим признакам — обычный вопрос: есть
    #     подлежащее, сказуемое и ни одного знакомого приказа. Разобранная
    #     общим путём, она уходила бы к модели, та вежливо отвечала «хорошо,
    #     запомнил» — и не запоминала ничего.
    запомнить = extract_memory(text)
    if запомнить is not None:
        return Decision(
            kind='remember',
            memory=запомнить,
            reason=f"просьба запомнить: «{запомнить}»",
            intent=intent,
        )

    # 0.6 Отложенная команда: «через час запусти рендер».
    #
    #     Стоит до общего разбора, и это выяснилось живой проверкой: фраза
    #     «через минуту открой блокнот» выполнялась НЕМЕДЛЕННО. Разбор видел
    #     знакомое «открой блокнот», а слова о времени считал шумом — блокнот
    #     открывался тут же, вместо того чтобы открыться через минуту.
    #
    #     От напоминания отличается глаголом: «напомни выключить компьютер» —
    #     слова в назначенный час, «выключи компьютер через час» — дело.
    отложено = extract_schedule(text)
    if отложено is not None:
        когда, приказ = отложено
        return Decision(
            kind='schedule',
            when=когда,
            order=приказ,
            reason=f"отложено на {когда:%d.%m %H:%M}: «{приказ}»",
            intent=intent,
        )

    # 0.7 «Открой проект такой-то».
    #
    #     Стоит до разбора команд, потому что общий разборщик видит «открой» и
    #     принимается искать программу с названием «проект скотт» — которой,
    #     разумеется, нет. Проект же — это папка, которую Scott знает по имени.
    проект = extract_project(text)
    if проект is not None:
        return Decision(
            kind='project',
            project=проект,
            reason=f"просьба открыть проект «{проект}»",
            intent=intent,
        )

    # 1. Названный сервис — самый надёжный признак из всех. Упоминание YouTube
    #    или GitHub однозначно говорит о намерении, и рисковать тем, что общая
    #    логика «вопрос или команда» переклассифицирует фразу, незачем: на
    #    пересечении их словарей уже не раз ловились ошибки.
    for service, markers, filler in WEB_SERVICES:
        if any(marker in lower for marker in markers):
            if intent.is_question and not intent.is_command:
                return Decision(kind='question', intent=intent, reason='вопрос о веб-сервисе')
            query = extract_web_query(text, filler | SITE_WORDS)
            return Decision(
                kind='web',
                service=service,
                query=query,
                reason=f"назван {service}" + (f", искать «{query}»" if query else ", открыть сайт"),
                intent=intent,
            )

    # 2. Вопросительное слово в начале сильнее глагола в середине.
    #
    #    «Чем открыть pdf» — вопрос о том, какой программой это делается, а не
    #    просьба запустить программу «чем pdf». Движок намерений видел глагол
    #    «открыть» и объявлял фразу приказом, после чего проверка «вопрос ли
    #    это» не выполнялась вовсе: она стоит ниже, под условием «если не
    #    приказ».
    if starts_with_question_word(lower) and intent.intent_type in PROGRAM_ACTION_TYPES:
        return Decision(
            kind='question',
            reason=f"начинается с вопросительного слова — спрашивают, а не приказывают "
                   f"(разбор предлагал {intent.intent_type})",
            intent=intent,
        )

    # 2а. Ответ знает сам Scott — значит это не вопрос к модели.
    #
    #     «Сколько места на диске» и «какие процессы запущены» по форме вопросы,
    #     и проверка ниже уводила их в модель. Она отвечала статьёй о том, как
    #     посмотреть место на диске, вместо того чтобы его посмотреть — знать,
    #     сколько его на этой машине, она не может.
    if intent.intent_type in SELF_ANSWERABLE:
        parsed = parser.parse(text)
        parsed.command_type = intent.intent_type
        parsed.main_param = intent.main_param

        return Decision(
            kind='action',
            action=intent.intent_type,
            parsed=parsed,
            reason=f"спрашивают об этой машине — Scott смотрит сам ({intent.intent_type})",
            intent=intent,
        )

    # 3. Вопрос — если это не явный приказ. Порядок важен: «Можешь открыть
    #    блокнот?» оформлено вопросом, но is_command об этом знает.
    if not intent.is_command and (getattr(intent, 'is_question', False) or starts_with_question_word(lower)
                                  or answerer.is_question(text)):
        return Decision(kind='question', reason="вопрос по форме", intent=intent)

    # 4. Разбор команды. Если намерение уверено, что это приказ, сначала
    #    снимаем вежливую обёртку: разборщик заметно надёжнее на чистом
    #    императиве («открой блокнот»), чем на «Скотт, можешь открыть блокнот?».
    command_text = strip_command_wrapper(text)
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

    if intent.intent_type == 'system_command' and intent.main_param in SYSTEM_ACTIONS:
        # Намерение разобралось до конкретного действия, разбор — нет. Два
        # случая, и оба чинятся здесь: «выключи компьютер» уезжало в close_app,
        # где Scott искал программу с таким названием и не находил её, а
        # «убавь яркость» доходило до исполнителя с параметром «убавь».
        parsed.command_type = 'system_command'
        parsed.main_param = intent.main_param
        notes.append(f"системная команда: {intent.main_param}")

    if intent.intent_type in INTENT_ALWAYS_WINS:
        # «Напомни через час открыть почту»: разборщик видит «открыть почту» и
        # предлагает сделать это сейчас — то есть ровно не то, о чём просили.
        # То же с «напиши программу на C»: там видят «программу» и пытаются её
        # запустить.
        parsed.command_type = intent.intent_type
        parsed.main_param = intent.main_param
        notes.append(f"намерение сильнее разбора ({intent.intent_type})")

    explicit_search = any(word in lower for word in EXPLICIT_SEARCH_WORDS)

    # 5. Поиск без просьбы искать — обычно всё-таки вопрос: «что такое яндекс»
    #    не значит «поищи в яндексе».
    if parsed.command_type == 'search' and not explicit_search and looks_like_question(text, intent):
        return Decision(
            kind='question',
            reason="разобрано как поиск, но по форме это вопрос",
            parsed=parsed,
            intent=intent,
        )

    # 6. Оболочку не выполняем никогда — проверка стоит раньше исполнения.
    # Удалить всё разом — отказ, а не молчаливое непонимание. Разбор такую
    # фразу не понимал и возвращал unknown: она уходила в модель, та отвечала
    # рассуждением об удалении файлов, и человек не знал, сделано или нет.
    if MASS_DELETE.search(lower):
        return Decision(
            kind='refused',
            reason="просят удалить всё разом",
            message=MASS_DELETE_REFUSAL,
            parsed=parsed,
            intent=intent,
        )

    if parsed.command_type in SHELL_TYPES:
        return Decision(
            kind='refused',
            reason=f"команда оболочки «{parsed.command_type}» через общий путь",
            message=SHELL_REFUSAL,
            parsed=parsed,
            intent=intent,
        )

    # 7. Выполнять или всё-таки отвечать.
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

    # 8. Ни вопрос по форме, ни знакомая команда. Короткая фраза скорее
    #    разговор, чем приказ, — на такие лучше ответить, чем сделать
    #    неизвестно что.
    if answerer.is_question(text) or len(lower.split()) <= 5:
        return Decision(
            kind='question',
            reason="не похоже на команду" + (" (короткая фраза)" if len(lower.split()) <= 5 else ""),
            parsed=parsed,
            intent=intent,
        )

    # 9. Последняя возможность: выполнить то, что разобралось.
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

    name_prefixes = ('скотт,', 'скотт ', 'скот,', 'скот ', 'скотти,', 'скотти ', 'scott,', 'scott ')
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


# Как люди просят запомнить.
#
# Проверяется начало фразы, а не вхождение где угодно: «я не помню, запомнил ли
# ты» — не просьба, а «напомни мне» — вовсе про напоминания, которые у Scott
# делает другая часть.
ЗАПОМНИТЬ = (
    "запомни, что",
    "запомни что",
    "запомни:",
    "запомни",
    "запиши, что",
    "запиши что",
    "имей в виду, что",
    "имей в виду что",
    "имей в виду",
)

# Слова, с которых просьба начинаться не может, даже если внутри есть «запомни».
НЕ_ЗАПОМНИТЬ = ("напомни", "не запоминай", "забудь")


def extract_memory(text: str):
    """
    Что человек просит запомнить, или None, если он ни о чём таком не просил.

    Возвращается именно содержание, без самого слова «запомни»: в память должно
    попасть «я работаю в вечернюю смену», а не «запомни, что я работаю в
    вечернюю смену» — последнее Scott потом пересказал бы модели как есть.
    """
    строка = (text or "").strip()
    низ = строка.lower()

    for запрет in НЕ_ЗАПОМНИТЬ:
        if низ.startswith(запрет):
            return None

    for начало in ЗАПОМНИТЬ:
        if низ.startswith(начало):
            остаток = строка[len(начало):].strip(" ,:—-")
            return остаток if остаток else None

    return None


# Как просят открыть проект.
#
# Слово «проект» обязательно: без него «открой скотт» — это просьба запустить
# программу, и отбирать её у обычного разбора нельзя.
ОТКРЫТЬ_ПРОЕКТ = (
    "открой проект",
    "открыть проект",
    "покажи проект",
    "перейди к проекту",
)


def extract_schedule(text: str):
    """
    Время и команда, если человек просит сделать что-то не сейчас.

    Возвращает пару (когда, что) или None. None — не «ошибка разбора», а
    обычный случай: большинство фраз о времени не просят ничего откладывать.

    Три условия, и все обязательны:

    * время названо явно — «через час», «в 7 утра», «завтра»;
    * это не просьба напомнить (там нужны слова, а не дело);
    * после вырезания времени осталась команда, а не пустота и не вопрос.
    """
    строка = (text or "").strip()
    if not строка:
        return None

    try:
        from . import reminders as reminders_module
        from . import scheduled as scheduled_module
    except ImportError:
        import reminders as reminders_module
        import scheduled as scheduled_module

    if scheduled_module.is_reminder(строка):
        return None

    когда = reminders_module.parse_time(строка)
    if когда is None:
        return None

    приказ = reminders_module.strip_time(строка)

    # Осталось слишком мало — значит время и было всей фразой: «через час»,
    # «в 7 утра». Откладывать нечего.
    if len(приказ.split()) < 2:
        return None

    # Вопрос о времени — не команда: «сколько времени осталось до полуночи»
    # спрашивают, а не приказывают.
    if starts_with_question_word(приказ.lower()):
        return None

    return когда, приказ


def extract_project(text: str):
    """Название проекта, который просят открыть, или None."""
    строка = (text or "").strip()
    низ = строка.lower()

    for начало in ОТКРЫТЬ_ПРОЕКТ:
        if низ.startswith(начало):
            остаток = строка[len(начало):].strip(" ,:—-«»\"")
            return остаток if остаток else None

    return None


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


def starts_with_question_word(text: str) -> bool:
    """
    Начинается ли фраза с вопросительного слова.

    Обращение в начале не считается: «Скотт, чем открыть pdf» — тот же вопрос,
    что и без обращения.
    """
    words = [
        w for w in re.sub(r'[^\w\s]+', ' ', text.lower(), flags=re.UNICODE).split()
        if w not in vocabulary.ADDRESS_WORDS
    ]
    if not words:
        return False

    # Двусловные вопросительные обороты («есть ли», «можно ли») проверяются
    # вместе — по одному слову они ничего не значат.
    начало_двух = ' '.join(words[:2])
    return words[0] in QUESTION_KEYWORDS or начало_двух in QUESTION_KEYWORDS


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
