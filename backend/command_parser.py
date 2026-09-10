"""
Расширенный парсер команд с NLP
Понимает естественный язык и парсит команды
"""

import re

import vocabulary
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass


@dataclass
class ParsedCommand:
    """Структура распарсенной команды"""
    command_type: str  # search, open_app, create_file, get_info, etc.
    main_param: str    # Основной параметр команды
    context: Dict      # Дополнительный контекст
    confidence: float  # Уверенность в парсинге (0-1)
    
    def __repr__(self):
        return f"ParsedCommand(type={self.command_type}, param={self.main_param}, conf={self.confidence:.2f})"


# Насколько точным считается совпадение.
#
# Число зависит только от того, что совпало, а не от длины списка, в котором
# нашлось. Раньше уверенность считалась как очки / (длина списка / 2): каждый
# добавленный синоним молча снижал уверенность для всего типа, а само число
# ничего не значило — за одинаково ложные совпадения «поисковик» получал 0.21,
# а «сайтостроение» 0.67.
MULTIWORD_MATCH = 0.9      # «создай папку» — сомнений почти нет
WORD_MATCH = 0.75          # «закрой» — обычное совпадение
SHORT_MATCH = 0.6          # «run», «cd» — короткое слово легко случайно
KNOWN_APP_BONUS = 0.1      # знакомое название программы рядом с глаголом
BARE_APP_NAME = 0.5        # одно название без глагола


def _match_confidence(matched: str) -> float:
    """Насколько точно совпадение описывает просьбу."""
    if len(matched.split()) >= 2:
        return MULTIWORD_MATCH
    return WORD_MATCH if len(matched) > 3 else SHORT_MATCH


def _longest_match(text: str, synonyms) -> str:
    """
    Самое длинное совпавшее выражение — или пустая строка.

    Длинное точнее короткого: во фразе «создай папку отчёты» совпадают и
    «создай папку», и «создай», и выбрать нужно первое.
    """
    best = ''
    for synonym in synonyms:
        if len(synonym) > len(best) and vocabulary.has_word(text, synonym):
            best = synonym
    return best


class CommandParser:
    """Умный парсер команд с поддержкой естественного языка"""
    
    # Синонимы команд
    COMMAND_SYNONYMS = {
        # Поиск информации (ТОЛЬКО явные команды поиска, НЕ вопросы!)
        'search': list(vocabulary.SEARCH_WORDS),
        
        # Открыть приложение
        # «Нужна программа» — не глагол, а оборот; поэтому список глаголов
        # берётся общий, а этот случай добавляется рядом.
        'open_app': list(vocabulary.LAUNCH_VERBS) + ['нужна программа'],
        
        # Создать файл
        # Объект обязателен: что именно создать.
        #
        # Голые «создай», «создать» и «напиши» отсюда убраны. С ними любая
        # просьба что-нибудь сделать превращалась в файл: «создай программу
        # занятий для новичка» заводило пустой файл с таким именем и
        # рапортовало об успехе, а «напиши письмо начальнику» — файл «письмо
        # начальнику» вместо самого письма.
        'create_file': list(vocabulary.CREATE_FILE_PHRASES),
        
        # Создать папку
        'create_folder': list(vocabulary.CREATE_FOLDER_PHRASES),
        
        # Информация о системе
        'system_info': [
            'статус системы', 'как система', 'CPU', 'RAM',
            'сколько свободно', 'система', 'память',
            'system info', 'how much ram', 'cpu usage'
        ],
        
        # Браузер действия
        'open_website': [
            'открой сайт', 'перейди', 'сайт',
            'open website', 'go to', 'website'
        ],
        
        # Валюты и криптография
        'get_currency': [
            'курс доллара', 'курс евро', 'сколько доллар',
            'сколько евро', 'bitcoin', 'биткоин',
            'exchange rate', 'dollar', 'euro', 'btc'
        ],
        
        # Погода
        'get_weather': [
            'погода', 'как погода', 'сейчас', 'температура',
            'weather', 'temperature', 'is it raining'
        ],
        
        # Новости
        'get_news': [
            'новости', 'последние новости', 'что нового',
            'news', 'latest news', 'breaking news'
        ],
        
        # Управление окнами
        'manage_window': [
            'свернуть', 'развернуть', 'закрыть окно',
            'minimize', 'maximize', 'close window',
            'alt+tab', 'next window'
        ],
        
        # Закрыть приложение
        'close_app': list(vocabulary.CLOSE_VERBS),
        
        # PowerShell команды
        'powershell': [
            'powershell', 'пауэршел', 'команда', 'bat', 'батник',
            'execute command', 'run command', 'выполни', 'запусти команду'
        ],
        
        # Файловые операции
        # Операции над файлами — именно операции.
        #
        # Отсюда убраны «открой папку» и «open folder»: открыть папку — не
        # операция над файлом, для этого есть свой тип, и путались они всерьёз.
        # Убраны и голые существительные «файл» и «документ»: по ним в эту
        # ветку уходила любая фраза, где встретилось слово «файл».
        'file_operation': [
            'удали файл', 'удалить файл', 'скопируй', 'скопировать',
            'переместить', 'перемести', 'переименуй', 'скачать', 'скачай',
            'delete file', 'copy file', 'move file', 'download file',
            'создать документ', 'новый документ',
        ],
        
        # Системные команды
        'system_command': [
            'громкость', 'яркость', 'спящий режим', 'сон',
            'перезагрузка', 'отключение', 'выключение',
            'volume', 'brightness', 'sleep', 'hibernate',
            'restart', 'shutdown', 'turn off', 'увеличь громкость', 'уменьши громкость'
        ],
        
        # Запуск скриптов
        'run_script': [
            'запусти скрипт', 'выполни скрипт', 'скрипт',
            'python скрипт', 'node скрипт', 'javascript',
            'run script', 'execute script', 'python', 'node', 'js'
        ],
        
        # Открыть URL
        'open_url': [
            'открой ссылку', 'перейди по ссылке', 'ссылка',
            'open link', 'go to link', 'url', 'http'
        ],
    }
    
    # Стоп-слова которые не важны для парсинга
    # Слова, которые в живой речи есть всегда, а к сути команды отношения не
    # имеют. Без них «открой мне пожалуйста дискорд» превращалось в поиск
    # программы с названием «мне дискорд» — и, разумеется, ничего не находило.
    STOP_WORDS = {
        'и', 'или', 'что', 'это', 'его', 'её', 'их',
        'а', 'в', 'во', 'не', 'да', 'по', 'для',
        'пожалуйста', 'спасибо', 'скотт', 'scott',
        'the', 'a', 'an', 'is', 'are', 'am', 'be',

        # Обращения и вежливые обороты
        'мне', 'мой', 'моя', 'моё', 'нам', 'ка', 'же', 'бы', 'ну',
        'слушай', 'слышишь', 'эй', 'привет', 'давай', 'давайка',
        'можешь', 'сможешь', 'помоги', 'быстро', 'сейчас', 'сюда',
        'плиз', 'плз', 'будь', 'добр', 'любезен',

        # Слова-паразиты, которые Whisper исправно записывает
        'короче', 'значит', 'типа', 'вот', 'просто', 'там', 'тут',
    }
    
    # Глаголы запуска. Отдельным списком — им пользуется вырезание глагола из
    # параметра. Особого порядка проверки у запуска больше нет: все типы
    # считаются по одной формуле, и выигрывает самое точное совпадение.
    OPEN_APP_VERBS = vocabulary.LAUNCH_VERBS

    # Названия, по которым сразу понятно, что речь о программе.
    KNOWN_APP_NAMES = vocabulary.KNOWN_APP_NAMES

    def __init__(self):
        print("✅ Парсер команд инициализирован")
    
    def parse(self, user_input: str) -> ParsedCommand:
        """
        Главный метод парсинга
        Преобразует текст пользователя в структурированную команду
        """
        text = user_input.lower().strip()
        
        # Определяем тип команды
        command_type, confidence = self._detect_command_type(text)
        
        # Извлекаем параметры
        main_param = self._extract_parameter(text, command_type)
        
        # Дополнительный контекст
        context = self._extract_context(text, command_type)
        
        return ParsedCommand(
            command_type=command_type,
            main_param=main_param,
            context=context,
            confidence=confidence
        )
    
    # Типы, для которых знакомое название программы — довод в их пользу.
    APP_TYPES = ('open_app', 'close_app')

    def _detect_command_type(self, text: str) -> Tuple[str, float]:
        """
        Определить тип команды.

        Уверенность зависит только от того, что совпало: многословное выражение
        точнее одного слова, длинное слово точнее короткого. От длины списка
        синонимов она не зависит — иначе добавление синонима молча меняло бы
        поведение всего типа.
        """
        best_type = 'unknown'   # search должен быть явным, поэтому не он
        best_confidence = 0.0
        best_length = 0

        app_named = any(vocabulary.has_word(text, name) for name in self.KNOWN_APP_NAMES)

        for command_type, synonyms in self.COMMAND_SYNONYMS.items():
            matched = _longest_match(text, synonyms)
            if not matched:
                continue

            confidence = _match_confidence(matched)

            # Знакомое название рядом с глаголом снимает последние сомнения:
            # «открой браузер» надёжнее, чем просто «открой».
            if app_named and command_type in self.APP_TYPES:
                confidence = min(confidence + KNOWN_APP_BONUS, 1.0)

            # При равной уверенности выигрывает более длинное совпадение:
            # «открой сайт» точнее, чем «открой».
            if (confidence, len(matched)) > (best_confidence, best_length):
                best_type = command_type
                best_confidence = confidence
                best_length = len(matched)

        # Название программы без единого глагола — всё-таки просьба её открыть:
        # на «дискорд» человек ждёт запуска, а не рассказа о программе. Но
        # решается это последним, когда ни один тип не подошёл.
        if best_type == 'unknown' and app_named:
            return 'open_app', BARE_APP_NAME

        return best_type, best_confidence

    def _extract_parameter(self, text: str, command_type: str) -> str:
        """Извлечь основной параметр команды"""
        
        # Удаляем синонимы КОМАНДЫ ЭТОГО ЖЕ типа из текста — раньше здесь
        # проходились .values() по ВСЕМ категориям сразу, поэтому, например,
        # 'google' (синоним из категории 'search') вырезался даже из команды
        # open_app «открой google chrome», и резолвер получал на вход обрубок
        # «chrome» вместо «google chrome».
        # Вырезаются они ПО ГРАНИЦАМ СЛОВ и начиная с самых длинных. Простой
        # replace() резал синоним внутри другого слова: в «запустить
        # дельторуна» находилось «запусти», и резолвер получал на вход «ть
        # дельторуна» — приложение, разумеется, не находилось.
        clean_text = text
        for synonym in sorted(self.COMMAND_SYNONYMS.get(command_type, []), key=len, reverse=True):
            clean_text = re.sub(rf"\b{re.escape(synonym)}\b", " ", clean_text)
        
        # Удаляем стоп-слова
        words = clean_text.split()
        words = [w.strip() for w in words if w.strip() and w.lower() not in self.STOP_WORDS]
        
        # Специфическая логика для каждого типа команды
        if command_type == 'get_currency':
            if 'доллар' in text or 'dollar' in text or 'usd' in text:
                return 'dollar'
            elif 'евро' in text or 'euro' in text or 'eur' in text:
                return 'euro'
            elif 'bitcoin' in text or 'биткоин' in text or 'btc' in text:
                return 'bitcoin'
        
        elif command_type == 'get_weather':
            # Ищем название города
            cities = ['москва', 'moscow', 'спб', 'санкт-петербург', 'питер', 'новосибирск']
            for city in cities:
                if city in text:
                    return city
            return 'moscow'  # Default
        
        elif command_type == 'open_app':
            # Раньше здесь был жёсткий список приложений — убран: помимо
            # необходимости ручного пополнения, он ещё и ломался на подстроках
            # ("notepad" совпадал раньше "notepad++"). Вместо этого используем
            # общий fallback ниже (clean_text/words: исходный текст без
            # глаголов-синонимов команды и стоп-слов) — он и так корректно
            # выделяет название приложения, а резолвинг (app_resolver.py)
            # ищет ЛЮБОЕ установленное приложение без списка.
            pass

        elif command_type == 'system_command':
            # Системные команды
            if any(word in text for word in ['громкость', 'volume', 'звук']):
                if any(word in text for word in ['увеличь', 'повыси', 'up', 'increase', '+']):
                    return 'volume_up'
                elif any(word in text for word in ['уменьши', 'понизь', 'down', 'decrease', '-']):
                    return 'volume_down'
                else:
                    return 'volume_get'
            
            elif any(word in text for word in ['яркость', 'brightness']):
                if any(word in text for word in ['увеличь', 'повыси', 'up', 'increase']):
                    return 'brightness_up'
                elif any(word in text for word in ['уменьши', 'понизь', 'down', 'decrease']):
                    return 'brightness_down'
            
            elif any(word in text for word in ['сон', 'sleep', 'спящий режим', 'hibernate']):
                return 'sleep'
            
            elif any(word in text for word in ['перезагрузка', 'restart', 'перезагрузи']):
                return 'restart'
            
            elif any(word in text for word in ['отключение', 'выключение', 'shutdown', 'отключи']):
                return 'shutdown'
        
        elif command_type == 'file_operation':
            # Файловые операции
            if any(word in text for word in ['открой папку', 'папка', 'folder', 'directory']):
                return 'open_folder'
            elif any(word in text for word in ['удали', 'delete', 'удалить']):
                return 'delete_file'
            elif any(word in text for word in ['скопируй', 'copy', 'скопировать']):
                return 'copy_file'
            elif any(word in text for word in ['переместить', 'move', 'move file']):
                return 'move_file'
            elif any(word in text for word in ['скачать', 'download', 'загрузить']):
                return 'download_file'
        
        elif command_type == 'search':
            # Из запроса выкидывается всё, что относится к самой просьбе
            # искать: глагол, место («в поиске браузера») и предлоги. Иначе
            # Scott искал «введи браузера рецепт борща» вместо рецепта борща.
            kept = [
                w for w in words
                if w.lower().strip('.,!?:;—-') not in vocabulary.SEARCH_FILLER_WORDS
            ]
            return ' '.join(kept) if kept else (' '.join(words) or 'неизвестно')

        elif command_type == 'powershell':
            # Оставить всё что осталось как команда
            return ' '.join(words) if words else 'unknown_command'
        
        elif command_type == 'run_script':
            # Название скрипта/языка
            if 'python' in text:
                return 'python'
            elif 'node' in text or 'javascript' in text or 'js' in text:
                return 'node'
            return ' '.join(words) if words else 'unknown_script'
        
        elif command_type == 'open_url':
            # Найти URL
            urls = re.findall(r'http[s]?://[^\s]+|www\.[^\s]+', text)
            if urls:
                return urls[0]
            # Иначе вернуть оставшиеся слова
            return ' '.join(words) if words else 'unknown_url'
        
        # Общий случай - берём всё что осталось
        if words:
            return ' '.join(words)
        
        return 'неизвестно'
    
    def _extract_context(self, text: str, command_type: str) -> Dict:
        """Извлечь дополнительный контекст"""
        context = {
            'language': 'ru' if self._is_russian(text) else 'en',
            'is_polite': any(word in text for word in ['пожалуйста', 'please', 'спасибо']),
            'is_urgent': any(word in text for word in ['срочно', 'быстро', 'immediately', 'asap']),
        }
        
        # Ищем дополнительные параметры
        if 'на рабочий стол' in text or 'on desktop' in text:
            context['location'] = 'desktop'
        
        if 'в блокнот' in text or 'notepad' in text:
            context['app'] = 'notepad'
        
        return context
    
    def _is_russian(self, text: str) -> bool:
        """Проверить есть ли русские буквы"""
        return any('\u0400' <= char <= '\u04FF' for char in text)
    
    def parse_multiple_commands(self, text: str) -> List[ParsedCommand]:
        """Парсить несколько команд из одного текста"""
        # Разделяем по запятой или 'и'
        parts = re.split(r',|и(?=\s)', text)
        
        commands = []
        for part in parts:
            part = part.strip()
            if part:
                commands.append(self.parse(part))
        
        return commands if commands else [self.parse(text)]
    
    def __repr__(self):
        return f"CommandParser(synonyms={len(self.COMMAND_SYNONYMS)}, stop_words={len(self.STOP_WORDS)})"


def get_command_parser() -> CommandParser:
    """Factory функция для получения парсера"""
    return CommandParser()
