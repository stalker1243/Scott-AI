"""
Расширенный парсер команд с NLP
Понимает естественный язык и парсит команды
"""

import re
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


def _has_word(text: str, word: str) -> bool:
    """
    Есть ли слово в тексте целиком, а не куском другого слова.

    Простое вхождение подводит на приставках: «включи» находится внутри
    «ВЫключи», и просьба выключить музыку превращалась в просьбу её включить.
    """
    return re.search(r"(?<![^\W\d_])" + re.escape(word) + r"(?![^\W\d_])", text) is not None


class CommandParser:
    """Умный парсер команд с поддержкой естественного языка"""
    
    # Синонимы команд
    COMMAND_SYNONYMS = {
        # Поиск информации (ТОЛЬКО явные команды поиска, НЕ вопросы!)
        'search': [
            'поиск', 'найди', 'гугли', 'ищи', 'найдите',
            'search for', 'find', 'look for', 'google',
            'поиск в интернете', 'поискать',
            'гугль', 'яндекс', 'yandex'
        ],
        
        # Открыть приложение
        'open_app': [
            'открой', 'запусти', 'включи', 'запустите', 'откройте',
            'открыть', 'запустить', 'включить',
            'open', 'launch', 'start', 'run', 'exec',
            'нужна программа', 'запустить'
        ],
        
        # Создать файл
        # Объект обязателен: что именно создать.
        #
        # Голые «создай», «создать» и «напиши» отсюда убраны. С ними любая
        # просьба что-нибудь сделать превращалась в файл: «создай программу
        # занятий для новичка» заводило пустой файл с таким именем и
        # рапортовало об успехе, а «напиши письмо начальнику» — файл «письмо
        # начальнику» вместо самого письма.
        'create_file': [
            'создай файл', 'создать файл', 'создайте файл', 'новый файл',
            'создай новый файл', 'сделай файл',
            'create file', 'make file', 'new file',
        ],
        
        # Создать папку
        'create_folder': [
            'создай папку', 'создать папку', 'создайте папку', 'новая папка',
            'создай новую папку', 'сделай папку',
            'создай директорию', 'создать директорию', 'создай каталог',
            'create folder', 'make folder', 'create directory', 'mkdir', 'new folder',
        ],
        
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
        'close_app': [
            'закрой', 'закройте', 'выключи', 'заверши',
            'close', 'quit', 'exit', 'kill'
        ],
        
        # PowerShell команды
        'powershell': [
            'powershell', 'пауэршел', 'команда', 'bat', 'батник',
            'execute command', 'run command', 'выполни', 'запусти команду'
        ],
        
        # Файловые операции
        'file_operation': [
            'открой папку', 'открыть папку', 'файл', 'документ',
            'удали файл', 'скопируй', 'переместить', 'скачать',
            'open folder', 'delete file', 'copy', 'move', 'download',
            'создать документ', 'новый документ'
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
    
    # Глаголы запуска. Держим отдельным списком, а не среди синонимов, потому
    # что запуск проверяется раньше остальных типов.
    OPEN_APP_VERBS = [
        'открой', 'откройте', 'открыть',
        'запусти', 'запустите', 'запустить',
        'включи', 'включить',
        'open', 'launch', 'start', 'run', 'exec',
    ]

    # Названия, по которым сразу понятно, что речь о программе.
    KNOWN_APP_NAMES = [
        'notepad', 'chrome', 'code', 'vscode', 'cmd', 'powershell', 'paint',
        'word', 'excel', 'telegram', 'discord', 'spotify', 'browser',
        'блокнот', 'проводник', 'калькулятор', 'браузер', 'хром', 'ворд',
        'эксель', 'телеграм', 'дискорд', 'спотифай', 'паинт',
    ]

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
    
    def _detect_command_type(self, text: str) -> Tuple[str, float]:
        """Определить тип команды из текста"""
        max_score = 0
        best_command = 'unknown'  # Default; search должен быть явным
        
        # Запуск программы проверяется отдельно от прочих типов: слов-глаголов
        # для него много, и по общей формуле он проигрывал бы там, где должен
        # выигрывать. Но очки обязаны быть в той же шкале, что у остальных, —
        # от нуля до единицы. Раньше они были сырыми (за глагол 2, за знакомую
        # программу +3), и open_app побеждал ВСЕГДА, стоило человеку назвать
        # программу: «закрой дискорд» разбиралось как запуск дискорда.
        open_app_score = 0.0

        if any(_has_word(text, keyword) for keyword in self.OPEN_APP_VERBS):
            open_app_score = 0.9

            # Знакомое название рядом с глаголом снимает последние сомнения.
            if any(_has_word(text, name) for name in self.KNOWN_APP_NAMES):
                open_app_score = 1.0

        if open_app_score > 0:
            max_score = open_app_score
            best_command = 'open_app'

        # Проверяем каждый тип команды
        for command_type, synonyms in self.COMMAND_SYNONYMS.items():
            if command_type == 'open_app':
                continue  # Уже проверили выше с приоритетом
                
            score = 0
            found_count = 0
            
            for synonym in synonyms:
                if synonym in text:
                    found_count += 1
                    # Даём разный вес слов
                    if len(synonym) > 3:
                        score += 2
                    else:
                        score += 1
            
            if found_count > 0:
                confidence = min(score / (len(synonyms) / 2), 1.0)
                if confidence > max_score:
                    max_score = confidence
                    best_command = command_type

        # Название программы без единого глагола — это всё-таки просьба её
        # открыть: на «дискорд» человек ждёт запуска, а не вопроса к ИИ. Но
        # решается это в последнюю очередь, когда ни один тип не подошёл, а не
        # вперёд всех остальных.
        if best_command == 'unknown' and any(_has_word(text, name) for name in self.KNOWN_APP_NAMES):
            return 'open_app', 0.5

        return best_command, max_score
    
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
