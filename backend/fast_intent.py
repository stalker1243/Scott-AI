"""
Fast intent engine for Scott AI.
Обрабатывает текст запроса очень быстро и определяет:
- вопрос ли это
- явный ли это поиск
- команда ли это
- тип команды (погода, поиск, открытие приложения и т.п.)
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class IntentResult:
    intent_type: str
    intent_subtype: Optional[str]
    main_param: str
    confidence: float
    is_question: bool
    is_search: bool
    is_explicit_search: bool
    is_command: bool
    is_system: bool

    def __repr__(self):
        return (
            f"IntentResult(type={self.intent_type}, subtype={self.intent_subtype}, "
            f"param={self.main_param!r}, conf={self.confidence:.2f}, "
            f"question={self.is_question}, search={self.is_search}, "
            f"explicit_search={self.is_explicit_search}, command={self.is_command})"
        )


class FastIntentEngine:
    # Примечание: голое 'google' сюда намеренно не включено — оно ложно
    # срабатывало на "открой Google Chrome" (это open_app, а не поиск).
    SEARCH_PHRASES = [
        'найди', 'поиск', 'гугли', 'ищи', 'search for', 'find', 'look for',
        'поискать', 'гугль', 'яндекс', 'search', 'искать', 'посмотри'
    ]

    QUESTION_WORDS = [
        'что', 'какой', 'какая', 'какое', 'какие', 'кто', 'кого', 'кому',
        'когда', 'где', 'куда', 'откуда', 'почему', 'зачем', 'как', 'сколько',
        'который', 'чем', 'каким', 'чего', 'каково'
    ]

    INFO_PHRASES = [
        'расскажи мне', 'расскажи про', 'расскажи о', 'объясни про', 'объясни мне',
        'объясни', 'покажи', 'опиши', 'скажи мне', 'дай информацию', 'что такое', 'что это',
        'как дела', 'как ты', 'что ты умеешь', 'кто ты', 'что ты можешь'
    ]

    CONVERSATIONAL_PATTERNS = [
        r'^(?:скотт\s+)?как\s+(дела|ты|ты себя|поживаешь|настроение)\b',
        r'^(?:скотт\s+)?что\s+ты\s+(умеешь|можешь)\b',
        r'^(?:скотт\s+)?кто\s+ты\b',
        r'^(?:скотт\s+)?что\s+можешь\b',
    ]

    OPEN_APP_PHRASES = [
        'открой', 'запусти', 'включи', 'открыть', 'запустить', 'включить',
        'open', 'launch', 'start', 'run', 'exec'
    ]

    CREATE_FILE_PHRASES = [
        'создай файл', 'создай папку', 'создай директорию', 'создай', 'создать',
        'make file', 'create file', 'create folder', 'mkdir'
    ]

    # ВАЖНО про эти списки: они матчатся простым вхождением подстроки и проверяются
    # ДО того, как текст будет признан вопросом. Раньше здесь стояли голые
    # существительные ('память', 'температура', 'курс', 'файл', 'команда', 'сайт'),
    # из-за чего обычные вопросы классифицировались как команды к ОС и Scott
    # отвечал не тем:
    #   «Как устроена память человека?»          → выдавал загрузку RAM
    #   «При какой температуре кипит вода?»       → лез за прогнозом погоды
    #   «Что такое команда в спорте?»             → уходил в powershell-ветку
    # Теперь фразы требуют контекста: либо командный глагол, либо явное указание
    # на то, что речь о состоянии этой машины / текущих данных.
    WEATHER_PHRASES = [
        'погода', 'прогноз погоды', 'weather', 'forecast',
        'температура на улице', 'температура за окном',
    ]
    NEWS_PHRASES = ['новости', 'news', 'latest news', 'последние новости']
    CURRENCY_PHRASES = [
        'курс доллара', 'курс евро', 'курс валют', 'курс биткоина', 'курс рубля',
        'сколько стоит доллар', 'сколько стоит евро', 'exchange rate', 'bitcoin price',
    ]
    SYSTEM_INFO_PHRASES = [
        'статус системы', 'состояние системы', 'информация о компьютере',
        'загрузка cpu', 'загрузка процессора', 'нагрузка на процессор',
        'сколько памяти занято', 'занято памяти', 'свободно памяти',
        'использование памяти', 'загрузка памяти',
        'место на диске', 'свободное место на диске',
        'cpu usage', 'ram usage', 'disk space', 'system status',
    ]
    CLOSE_APP_PHRASES = ['закрой', 'выключи', 'заверши', 'close', 'quit', 'exit']
    FILE_OPERATION_PHRASES = [
        'удали файл', 'удали папку', 'скопируй файл', 'скопируй папку',
        'перемести файл', 'перемести папку', 'переименуй файл',
        'скачай файл', 'download file',
    ]
    POWERSHELL_PHRASES = [
        'powershell', 'пауэршел', 'выполни команду', 'запусти команду',
        'выполни скрипт', 'запусти скрипт', 'run command', 'батник',
    ]
    OPEN_URL_PHRASES = ['открой сайт', 'перейди на сайт', 'открой ссылку', 'http://', 'https://']

    QUESTION_PATTERN = re.compile(
        r'^(?:' + r'|'.join(re.escape(word) for word in QUESTION_WORDS) + r')[\s\?]',
        re.IGNORECASE
    )

    def detect(self, text: str) -> IntentResult:
        lower = text.lower().strip()
        explicit_search = any(phrase in lower for phrase in self.SEARCH_PHRASES)

        if explicit_search:
            return IntentResult(
                intent_type='search',
                intent_subtype='search',
                main_param=lower,
                confidence=1.0,
                is_question=self.is_question(lower),
                is_search=True,
                is_explicit_search=True,
                is_command=False,
                is_system=False
            )

        if self._matches_any(lower, self.OPEN_APP_PHRASES):
            return self._build_intent('open_app', lower)
        if self._matches_any(lower, self.CREATE_FILE_PHRASES):
            subtype = 'create_file' if 'файл' in lower or 'file' in lower else 'create_folder'
            return self._build_intent(subtype, lower)
        if self._matches_any(lower, self.WEATHER_PHRASES):
            return self._build_intent('get_weather', lower)
        if self._matches_any(lower, self.NEWS_PHRASES):
            return self._build_intent('get_news', lower)
        if self._matches_any(lower, self.CURRENCY_PHRASES):
            return self._build_intent('get_currency', lower)
        if self._matches_any(lower, self.SYSTEM_INFO_PHRASES):
            return self._build_intent('system_info', lower)
        if self._matches_any(lower, self.CLOSE_APP_PHRASES):
            return self._build_intent('close_app', lower)
        if self._matches_any(lower, self.FILE_OPERATION_PHRASES):
            return self._build_intent('file_operation', lower)
        if self._matches_any(lower, self.POWERSHELL_PHRASES):
            return self._build_intent('powershell', lower)
        if self._matches_any(lower, self.OPEN_URL_PHRASES):
            return self._build_intent('open_url', lower)

        if self.is_question(lower):
            return IntentResult(
                intent_type='question',
                intent_subtype=None,
                main_param=self.extract_topic(lower),
                confidence=0.9,
                is_question=True,
                is_search=False,
                is_explicit_search=False,
                is_command=False,
                is_system=False
            )

        if self._matches_any(lower, self.INFO_PHRASES):
            return IntentResult(
                intent_type='question',
                intent_subtype=None,
                main_param=self.extract_topic(lower),
                confidence=0.8,
                is_question=True,
                is_search=False,
                is_explicit_search=False,
                is_command=False,
                is_system=False
            )

        if self._matches_any(lower, self.SEARCH_PHRASES):
            return IntentResult(
                intent_type='search',
                intent_subtype='search',
                main_param=lower,
                confidence=0.7,
                is_question=False,
                is_search=True,
                is_explicit_search=False,
                is_command=False,
                is_system=False
            )

        return IntentResult(
            intent_type='unknown',
            intent_subtype=None,
            main_param=self.extract_topic(lower),
            confidence=0.0,
            is_question=False,
            is_search=False,
            is_explicit_search=False,
            is_command=False,
            is_system=False
        )

    def _matches_any(self, text: str, phrases) -> bool:
        return any(phrase in text for phrase in phrases)

    def _build_intent(self, intent_type: str, text: str) -> IntentResult:
        return IntentResult(
            intent_type=intent_type,
            intent_subtype=intent_type,
            main_param=self.extract_topic(text),
            confidence=0.95,
            is_question=self.is_question(text),
            is_search=False,
            is_explicit_search=False,
            is_command=True,
            is_system=intent_type in ('system_info', 'powershell')
        )

    def is_question(self, text: str) -> bool:
        text = text.strip()
        if not text:
            return False
        if text.endswith('?'):
            return True
        if self.QUESTION_PATTERN.search(text):
            return True
        if any(phrase in text for phrase in self.INFO_PHRASES):
            return True
        if any(re.search(pattern, text) for pattern in self.CONVERSATIONAL_PATTERNS):
            return True
        if text.startswith(('привет', 'здравствуй', 'добрый', 'hello', 'hi')):
            return True
        if text.startswith(('как дела', 'как ты')):
            return True
        return False

    def extract_topic(self, text: str) -> str:
        text = re.sub(r'[?!.]+', '', text).strip()
        for phrase in self.INFO_PHRASES + self.SEARCH_PHRASES + self.QUESTION_WORDS:
            if text.startswith(phrase):
                text = text[len(phrase):].strip()
                break
        text = re.sub(r'^(что[- ]*нибудь|что[- ]*то)\s+', '', text)
        text = re.sub(r'^(о|об|про|на|в|такое|это)\s+', '', text)
        words = text.split()
        return ' '.join(words[:5]) if words else text


_fast_intent_engine = None


def get_fast_intent_engine() -> FastIntentEngine:
    global _fast_intent_engine
    if _fast_intent_engine is None:
        _fast_intent_engine = FastIntentEngine()
    return _fast_intent_engine
