"""
Интеллектуальный ответчик на вопросы
Обрабатывает вопросы и предоставляет информированные ответы
"""

import re
from contextlib import nullcontext
from datetime import datetime
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
import psutil
import platform

# Замеры этапов — необязательная зависимость: если модуль недоступен
# (например, файл импортируют отдельно в тестах), просто не замеряем.
try:
    from timing import stage as _timing_stage
except Exception:  # pragma: no cover
    def _timing_stage(name, meta=None):
        return nullcontext()


@dataclass
class Question:
    """Структура распарсенного вопроса"""
    question_type: str  # what, who, when, where, why, how, other
    subject: str        # О чём вопрос
    context: Dict       # Дополнительный контекст
    original: str       # Исходный текст


class QuestionAnswerer:
    """Интеллектуальный ответчик на вопросы"""
    
    # Вопросительные слова
    QUESTION_WORDS = {
        'what': ['что', 'какой', 'какая', 'какое', 'какие', 'what', 'which'],
        'who': ['кто', 'кого', 'кому', 'who', 'whom'],
        'when': ['когда', 'во сколько', 'в какое время', 'when', 'what time'],
        'where': ['где', 'куда', 'откуда', 'where', 'to where', 'from where'],
        'why': ['почему', 'зачем', 'why', 'what for'],
        'how': ['как', 'каким образом', 'how', 'in what way'],
        'how_much': ['сколько', 'как много', 'how much', 'how many'],
    }

    # Быстрые описания для популярных языков программирования и технологий
    TECHNOLOGY_SUMMARIES = {
        'python': 'Python — интерпретируемый язык высокого уровня с простой читабельной синтаксисом. Он широко используется в веб‑разработке, автоматизации, анализе данных и машинном обучении; имеет богатый набор библиотек и большую сообщество.',
        'javascript': 'JavaScript — язык, ориентированный на веб: выполняется в браузере и на сервере (Node.js). Он отвечает за поведение страниц, динамику интерфейсов и часто используется совместно с HTML/CSS и фреймворками (React, Vue, Angular).',
        'java': 'Java — статически типизированный объектно‑ориентированный язык, популярный в корпоративных системах и Android. Программы компилируются в байт‑код и запускаются на JVM, что обеспечивает переносимость и стабильность.',
        'c++': 'C++ сочетает низкоуровневую эффективность с возможностями высокоуровневой абстракции. Часто применяется в системном программировании, игровых движках и там, где важна производительность и контроль памяти.',
        'c#': 'C# — современный язык от Microsoft для платформы .NET, удобный для разработки десктопных, веб и игровых приложений (Unity). Обладает строгой типизацией и развитой экосистемой инструментов.',
        'go': 'Go (Golang) — компилируемый язык от Google, ориентированный на простоту, быструю компиляцию и удобство работы с параллельностью. Часто используется для сетевых сервисов и микросервисов.',
        'ruby': 'Ruby — динамический язык с акцентом на удобочитаемость и продуктивность разработчика. Широко известен благодаря фреймворку Rails для быстрой веб‑разработки.',
        'rust': 'Rust — системный язык, обеспечивающий безопасность памяти без сборщика мусора. Подходит для разработки высокопроизводительных и безопасных приложений.',
    }

    # Общие краткие определения для научных и базовых понятий
    GENERAL_SUMMARIES = {
        'атом': 'Атом — наименьшая частица химического элемента, сохраняющая его химические свойства; состоит из ядра (протоны и нейтроны) и электронной оболочки.',
        'молекула': 'Молекула — устойчивое соединение двух или более атомов, связанных химическими связями; это минимальная частица вещества, обладающая его свойствами.',
        'клетка': 'Клетка — базовая структурная и функциональная единица живых организмов; содержит органеллы и генетический материал.',
        'энергия': 'Энергия — способность системы совершать работу; проявляется в разных формах: кинетическая, потенциальная, тепловая, химическая и др.',
        'сила': 'Сила — взаимодействие, которое изменяет движение тела или деформирует его; измеряется в ньютонах (N).',
        'молекула воды': 'Молекула воды состоит из двух атомов водорода и одного атома кислорода (H2O) и обладает полярностью, что обуславливает многие её свойства.',
    }

    # Ключевые слова для управления уровнем подробности ответа
    VERBOSITY_SHORT = ['коротко', 'кратко', 'короче', 'вкратце', 'максимально кратко']
    VERBOSITY_LONG = ['подробнее', 'более подробно', 'подробно', 'расскажи подробнее', 'еще подробнее', 'расширь']

    INFO_PHRASES = [
        'расскажи мне', 'расскажи про', 'расскажи о', 'объясни про',
        'расскажи', 'объясни', 'покажи', 'опиши',
        'скажи мне', 'дай информацию', 'почему', 'зачем', 'поясни', 'что это',
        'что такое'
    ]

    CONVERSATIONAL_QUESTION_PATTERNS = [
        r'^(?:скотт\s+)?как\s+(дела|ты|ты себя|поживаешь|настроение)\b',
        r'^(?:скотт\s+)?что\s+ты\s+(умеешь|можешь)\b',
        r'^(?:скотт\s+)?кто\s+ты\b',
        r'^(?:скотт\s+)?что\s+можешь\b',
    ]

    GREETING_RESPONSES = {
        'привет': 'Привет! Я Scott. Как дела? Чем я могу помочь?',
        'здравствуй': 'Здравствуйте! Я Scott. Чем я могу помочь?',
        'добрый день': 'Добрый день! Я Scott. Чем я могу помочь?',
        'добрый вечер': 'Добрый вечер! Я Scott. Чем я могу помочь?',
        'доброе утро': 'Доброе утро! Я Scott. Чем я могу помочь?',
        'hello': 'Hello! I am Scott. How can I help you?',
        'hi': 'Hi! I am Scott. How can I help you?',
    }
    
    # Встроенная база знаний для частых вопросов.
    #
    # ВАЖНО: здесь лежат regex-паттерны, а не подстроки. Раньше это были широкие
    # ключевые слова ('память', 'время', 'час', 'система', 'диск', 'версия',
    # 'как зовут'), которые искались подстрокой в ЛЮБОМ месте вопроса — и любой
    # содержательный вопрос перехватывался локальным обработчиком:
    #   «Как устроена память человека?»       → выдавалась загрузка RAM
    #   «Сколько времени занимает перелёт?»   → выдавалось время на компьютере
    #   «Чем Linux отличается от Windows?»    → выдавалась версия ОС пользователя
    #   «Как зовут президента Франции?»       → выдавалось имя пользователя Windows
    # Паттерны ниже требуют, чтобы вопрос был именно про эту машину или про
    # самого Scott; всё остальное уходит дальше — в LLM.
    KNOWLEDGE_BASE = {
        # Время и дата
        'time': {
            'keywords': [
                r'который\s+час', r'сколько\s+(?:сейчас\s+)?времени\s*[?!.]*$',
                r'текущее\s+время', r'^\s*время\s*[?!.]*$',
                r'what\s+time\s+is\s+it', r'current\s+time',
            ],
            'handler': 'get_current_time'
        },
        'date': {
            'keywords': [
                r'какой\s+(?:сейчас\s+|сегодня\s+)?день', r'какая\s+(?:сегодня\s+)?дата',
                r'какое\s+(?:сегодня\s+)?число', r'what\s+(?:date|day)\s+is',
            ],
            'handler': 'get_current_date'
        },

        # Система и информация — только про ЭТОТ компьютер
        'cpu': {
            'keywords': [
                r'(?:использование|загрузка|нагрузка\s+на)\s+(?:процессора|цп|cpu)',
                r'сколько\s+(?:занято\s+)?(?:процессора|cpu)',
                r'cpu\s+usage', r'загружен\s+ли\s+процессор',
            ],
            'handler': 'get_cpu_info'
        },
        'ram': {
            'keywords': [
                r'сколько\s+(?:занято|свободно|осталось)?\s*(?:оперативной\s+)?пам[яи]ти',
                r'(?:загрузка|использование|расход)\s+(?:оперативной\s+)?пам[яи]ти',
                r'how\s+much\s+ram', r'\bram\s+usage',
            ],
            'handler': 'get_ram_info'
        },
        'disk': {
            'keywords': [
                r'место\s+на\s+диске', r'сколько\s+(?:свободно|занято)\s+на\s+диске',
                r'свободное\s+место', r'disk\s+space', r'free\s+space',
            ],
            'handler': 'get_disk_info'
        },

        # Система
        'system': {
            'keywords': [
                r'кака[яй]\s+(?:у\s+меня\s+|на\s+компьютере\s+)?(?:операционная\s+)?система',
                r'кака[яй]\s+(?:у\s+меня\s+)?ос\b', r'what\s+os\b',
                r'верси[яю]\s+windows',
            ],
            'handler': 'get_os_info'
        },
        'pc_name': {
            'keywords': [
                r'как\s+называется\s+(?:мой\s+)?компьютер', r'имя\s+компьютера',
                r'computer\s+name', r'\bpc\s+name', r'имя\s+пк',
            ],
            'handler': 'get_pc_name'
        },
        'user': {
            'keywords': [
                r'имя\s+пользователя', r'под\s+каким\s+пользователем',
                r'user\s+name',
            ],
            'handler': 'get_user_name'
        },

        # Навыки и возможности
        'abilities': {
            'keywords': [
                r'что\s+ты\s+(?:можешь|умеешь|делаешь)', r'какие\s+(?:у\s+тебя\s+)?команды',
                r'тво[ии]\s+возможности', r'what\s+can\s+you\s+do',
            ],
            'handler': 'get_abilities'
        },
        'version': {
            'keywords': [
                r'кака[яй]\s+(?:у\s+тебя\s+)?верси[яи]', r'тво[яё]\s+верси[яи]',
                r'scott\s+version', r'верси[яи]\s+scott',
            ],
            'handler': 'get_version'
        },
    }
    
    def __init__(self):
        print("✅ Интеллектуальный ответчик на вопросы инициализирован")
    
    def is_question(self, text: str) -> bool:
        """Проверить, является ли текст вопросом"""
        text_lower = text.lower().strip()
        
        # Главный признак - вопросительный знак в конце
        if text_lower.endswith('?'):
            print(f"   ✓ is_question: endswith('?') → True")
            return True
        
        # Проверяем на фразы вида "что такое", "кто такой" и т.д.
        if any(phrase in text_lower for phrase in ['что такое', 'кто такой', 'кто такая']):
            print(f"   ✓ is_question: содержит 'что такое/кто такой' → True")
            return True
        
        # Проверяем на информационные запросы, которые не обязательно имеют вопросительный знак
        if any(phrase in text_lower for phrase in self.INFO_PHRASES):
            print(f"   ✓ is_question: содержит информационную фразу → True")
            return True

        # Проверяем разговорные вопросы вроде "как дела", "скотт как дела"
        if any(re.search(pattern, text_lower) for pattern in self.CONVERSATIONAL_QUESTION_PATTERNS):
            print(f"   ✓ is_question: conversational phrase → True")
            return True
        
        # Проверяем на приветствия и обычный разговор
        greetings = ['привет', 'привет,', 'привет ', 'здравствуй', 'здравствуй,', 'здравствуй ', 'hello', 'hi']
        question_words_in_text = ['как', 'какой', 'какая', 'что', 'кто', 'где', 'когда', 'почему', 'зачем', 'сколько']
        for greeting in greetings:
            if text_lower.startswith(greeting) and any(qw in text_lower for qw in question_words_in_text):
                print(f"   ✓ is_question: приветствие + вопрос → True")
                return True
            if text_lower.startswith(greeting):
                print(f"   ✓ is_question: приветствие/обычный разговор → True")
                return True
        
        # Проверяем, начинается ли с вопросительного слова
        for q_type, keywords in self.QUESTION_WORDS.items():
            for keyword in keywords:
                # Проверяем, начинается ли текст с вопросительного слова
                if text_lower.startswith(keyword + ' ') or text_lower.startswith(keyword + '?'):
                    print(f"   ✓ is_question: starts with '{keyword}' → True")
                    return True
        
        # Прямое совпадение с ключевыми словами локальной базы знаний (время,
        # дата, нагрузка ЦП и т.д.) — такие фразы почти никогда не оформлены
        # грамматически как вопрос ("который час" без "?"), но должны находить
        # мгновенный локальный ответ, а не улетать в LLM или падать в "не знаю".
        for kb_data in self.KNOWLEDGE_BASE.values():
            if any(re.search(pattern, text_lower) for pattern in kb_data['keywords']):
                print(f"   ✓ is_question: совпадение с локальной базой знаний → True")
                return True

        # Если нет ни одного совпадения - это не вопрос
        print(f"   ✗ is_question: не вопрос → False")
        return False
    
    def parse_question(self, text: str) -> Question:
        """Распарсить вопрос"""
        text_lower = text.lower().strip()
        
        # Определяем тип вопроса
        question_type = self._detect_question_type(text_lower)
        
        # Извлекаем тему вопроса
        subject = self._extract_subject(text_lower, question_type)
        
        # Контекст
        context = {
            'language': 'ru' if self._is_russian(text) else 'en',
            'is_polite': any(word in text_lower for word in ['пожалуйста', 'please']),
        }
        
        return Question(
            question_type=question_type,
            subject=subject,
            context=context,
            original=text
        )
    
    def answer(self, text: str) -> Optional[str]:
        """Ответить на вопрос"""
        if not self.is_question(text):
            return None

        # Безопасные значения по умолчанию — на случай, если исключение в try
        # ниже случится раньше, чем они будут по-настоящему вычислены;
        # используются в _ai_fallback, куда мы попадаем и из except-ветки.
        verbosity = 'normal'
        clean_text = text

        try:
            # Определить желаемый уровень подробности во входном тексте
            verbosity = self._detect_verbosity(text)
            # Удаляем указания на verbosity из текста чтобы не мешать анализу темы
            clean_text = self._strip_verbosity_markers(text)
            question = self.parse_question(clean_text)
            text_lower = clean_text.lower()
            print(f"   Detected verbosity: {verbosity}")
            # Для дальнейших шаблонов используем clean_text
            
            greeting_response = self._get_greeting_response(text_lower)
            if greeting_response:
                return greeting_response

            # 0. СНАЧАЛА проверяем расширенную базу ответов (ПРИОРИТЕТ!)
            try:
                import importlib
                try:
                    from .extended_responses import extended_responses
                except ImportError:
                    import extended_responses as extended_responses
                importlib.reload(extended_responses)
                extended_answer = extended_responses.try_extended_answer(text)
                if extended_answer:
                    print(f"✨ Расширенный ответ найден: {extended_answer[:120]}")
                    return extended_answer
            except ImportError:
                print("⚠️ Модуль extended_responses не найден")
            except Exception as e:
                print(f"⚠️ Ошибка при загрузке extended_responses: {e}")

            if any(re.search(pattern, text_lower) for pattern in self.CONVERSATIONAL_QUESTION_PATTERNS):
                base = 'У меня всё отлично! А у тебя?' if 'дела' in text_lower or 'как ты' in text_lower else 'Я готов помочь и ответить на твои вопросы.'
                return base if verbosity == 'normal' else (base if verbosity == 'long' else base.split('.')[0] + '.')
            
            # 1. Проверяем встроенную базу знаний
            for kb_key, kb_data in self.KNOWLEDGE_BASE.items():
                for keyword in kb_data['keywords']:
                    if re.search(keyword, text_lower):
                        handler_name = kb_data['handler']
                        handler = getattr(self, handler_name, None)
                        if handler:
                            try:
                                result = handler(question)
                                # Если пользователь просил коротко — сократить результат до первого предложения
                                if verbosity == 'short':
                                    sentences = re.split(r'(?<=[.!?])\s+', result.strip())
                                    return sentences[0] if sentences else result
                                return result
                            except Exception as e:
                                print(f"❌ Ошибка в обработчике {handler_name}: {e}")
                                return None
            
            # 2. Специфические обработки для разных типов вопросов
            if question.question_type == 'what':
                if 'что такое' in text_lower or 'что это' in text_lower:
                    subject = self._extract_subject(text_lower, 'what')
                    # Нормализуем subject
                    if subject:
                        subject_norm = subject.lower().strip().strip('.,!?:;')
                        # Если это известная технология — вернуть готовое описание
                        if subject_norm in self.TECHNOLOGY_SUMMARIES:
                            return self.TECHNOLOGY_SUMMARIES[subject_norm]

                    if subject and subject not in ['это', 'такое', 'что']:
                        # Нормализуем subject
                        subject_norm = subject.lower().strip().strip('.,!?:;')
                        # Проверяем общие определения
                        if subject_norm in self.GENERAL_SUMMARIES:
                            definition = self.GENERAL_SUMMARIES[subject_norm]
                            if verbosity == 'short':
                                sentences = re.split(r'(?<=[.!?])\s+', definition.strip())
                                return sentences[0] if sentences else definition
                            return definition
                        # Если это известная технология — вернуть подробное описание по умолчанию
                        if subject_norm in self.TECHNOLOGY_SUMMARIES:
                            long_desc = self.TECHNOLOGY_SUMMARIES[subject_norm]
                            if verbosity == 'short':
                                sentences = re.split(r'(?<=[.!?])\s+', long_desc.strip())
                                return sentences[0] if sentences else long_desc
                            return long_desc
                        # Ни в базе знаний, ни в словарях определений этого предмета нет.
                        # Раньше здесь возвращалась шаблонная пустышка ("X — это интересная
                        # тема!"), которая считалась полноценным ответом и не давала вопросу
                        # дойти до LLM — из-за этого на любой содержательный вопрос Scott
                        # отвечал отпиской за 50мс, ни разу не спросив модель.
                        ai_answer = self._ai_fallback(clean_text, verbosity)
                        if ai_answer:
                            return ai_answer
                        return f"Пока не знаю, что такое «{subject}». Могу поискать в интернете, если попросишь."
                if 'это' in text_lower or 'это?' in text_lower:
                    subject = question.subject
                    if subject:
                            subject_norm = subject.lower().strip().strip('.,!?:;')
                            if subject_norm in self.GENERAL_SUMMARIES:
                                definition = self.GENERAL_SUMMARIES[subject_norm]
                                if verbosity == 'short':
                                    sentences = re.split(r'(?<=[.!?])\s+', definition.strip())
                                    return sentences[0] if sentences else definition
                                return definition
                            if subject_norm in self.TECHNOLOGY_SUMMARIES:
                                long_desc = self.TECHNOLOGY_SUMMARIES[subject_norm]
                                if verbosity == 'short':
                                    sentences = re.split(r'(?<=[.!?])\s+', long_desc.strip())
                                    return sentences[0] if sentences else long_desc
                                return long_desc
                            # Та же причина, что и выше: не подменяем незнание отпиской,
                            # а отдаём вопрос модели.
                            ai_answer = self._ai_fallback(clean_text, verbosity)
                            if ai_answer:
                                return ai_answer
                            return f"Пока не знаю про «{subject}». Могу поискать в интернете, если попросишь."
            elif question.question_type == 'how_much':
                if 'весит' in text_lower or 'весить' in text_lower:
                    return "Я не имею информации о весе. Можешь помочь мне поискать в интернете?"

            # 3. Дополнительный шаблон для информационных запросов без конкретных ключевых слов
            if self._is_informational_request(text_lower):
                # "Расскажи про X" — раньше Scott отвечал встречным вопросом
                # ("что именно тебя интересует?") вместо того, чтобы рассказать.
                # Сначала пробуем модель, встречный вопрос оставляем только на
                # случай, когда LLM недоступен.
                ai_answer = self._ai_fallback(clean_text, verbosity)
                if ai_answer:
                    return ai_answer

                subject = self._extract_subject(text_lower, question.question_type)
                if subject and subject not in ['это', 'такое', 'что', 'неизвестно']:
                    prompt = f"Конечно, я могу рассказать про {subject}. Что именно тебя интересует: устройство, применение или историю?"
                    if verbosity == 'short':
                        return prompt.split('.')[0] + '.'
                    return prompt
                return "Конечно, я могу рассказать. О чем именно ты хочешь узнать?"

            # Ни одно встроенное правило не подошло — пробуем IntelligentAnswerer.
            return self._ai_fallback(clean_text, verbosity)

        except Exception as e:
            print(f"❌ Ошибка в answer(): {e}")
            import traceback
            traceback.print_exc()
            return self._ai_fallback(clean_text, verbosity)

    def _ai_fallback(self, clean_text: str, verbosity: str) -> Optional[str]:
        """
        Фоллбэк на IntelligentAnswerer, когда встроенные правила не дали ответа.

        Раньше этот код жил в блоке `finally` метода answer() — а `return` внутри
        `finally` в Python БЕЗУСЛОВНО подменяет собой любой return из try, включая
        уже найденный быстрый локальный ответ (приветствие, база знаний и т.д.).
        Из-за этого answer() на КАЖДЫЙ вопрос всегда делал ещё один сетевой вызов
        к LLM и отбрасывал результат локальной обработки, даже когда та уже дала
        мгновенный ответ — это была основная причина ощутимой задержки ответов.
        Плюс `finally` выполняется даже при раннем `return None` (текст не
        вопрос) до того, как clean_text вообще успевал быть присвоен — отсюда
        `UnboundLocalError: cannot access local variable 'clean_text'`.
        """
        try:
            # Импорт делаем внутри функции, чтобы избежать циклических зависимостей при загрузке
            try:
                from .intelligent_answerer import intelligent_answerer as ia
            except Exception:
                try:
                    from intelligent_answerer import intelligent_answerer as ia
                except Exception:
                    ia = None

            if ia and getattr(ia, 'enabled', False):
                try:
                    # Запрашиваем ответ у IA, учитывая требуемую подробность
                    with _timing_stage("ответ.llm"):
                        ai_resp = ia.answer_question(clean_text)
                    if ai_resp and isinstance(ai_resp, str):
                        # Вернуть первые 1-2 предложения для краткости и ясности
                        sentences = re.split(r'(?<=[.!?])\s+', ai_resp.strip())
                        if verbosity == 'short':
                            concise = sentences[0] if sentences else ai_resp
                            print(f"🧠 Fallback IA ответ (short): {concise}")
                            return concise
                        elif verbosity == 'long':
                            # Вернуть более развёрнутый ответ (до 5 предложений)
                            concise = ' '.join(sentences[:5]) if sentences else ai_resp
                            print(f"🧠 Fallback IA ответ (long): {concise[:200]}")
                            return concise
                        else:
                            # По умолчанию — подробный ответ (до 3 предложений)
                            concise = ' '.join(sentences[:3]) if sentences else ai_resp
                            print(f"🧠 Fallback IA ответ (default detailed): {concise[:200]}")
                            return concise
                except Exception as e:
                    print(f"⚠️ Ошибка при вызове intelligent_answerer: {e}")
        except Exception:
            pass
        return None

    def _detect_question_type(self, text: str) -> str:
        """Определить тип вопроса"""
        for q_type, keywords in self.QUESTION_WORDS.items():
            for keyword in keywords:
                if keyword in text:
                    return q_type
        return 'other'

    def _detect_verbosity(self, text: str) -> str:
        """Определить желаемый уровень подробности: 'short', 'normal', 'long'"""
        t = text.lower()
        for k in self.VERBOSITY_SHORT:
            if k in t:
                return 'short'
        for k in self.VERBOSITY_LONG:
            if k in t:
                return 'long'
        return 'normal'

    def _strip_verbosity_markers(self, text: str) -> str:
        """Удалить маркеры 'коротко'/'подробнее' из текста перед анализом"""
        t = text
        for k in self.VERBOSITY_SHORT + self.VERBOSITY_LONG:
            # убрать как отдельное слово или с запятой
            t = re.sub(r'\b' + re.escape(k) + r'\b', '', t, flags=re.IGNORECASE)
            t = re.sub(r',\s*' + re.escape(k), '', t, flags=re.IGNORECASE)
        return t.strip()
    
    def _extract_subject(self, text: str, question_type: str) -> str:
        """Извлечь тему вопроса"""
        original_text = text
        
        # Удаляем пунктуацию сначала
        text = text.replace('?', '').replace('!', '').strip()
        
        # Специально для "что такое X" вопросов
        if 'что такое' in text:
            # Извлекаем то, что идет после "что такое"
            subject = text.split('что такое', 1)[1].strip()
            if subject:
                return subject.split()[0]

        # Удаляем информационные фразы для извлечения темы
        for phrase in self.INFO_PHRASES:
            if text.startswith(phrase):
                text = text[len(phrase):].strip()
                break

        # Удаляем вводные слова и частицы после фразы
        text = re.sub(r'^(что[- ]*нибудь|что[- ]*то)\s+', '', text).strip()
        text = re.sub(r'^(о|об|про|на|в|такое|это)\s+', '', text).strip()

        if 'кто такой' in text or 'кто такая' in text:
            subject = text.replace('кто такой', '').replace('кто такая', '').replace('кто', '').strip()
            if subject:
                return subject.split()[0]
        
        # Для остальных вопросов - удаляем вопросительные слова
        for keywords in self.QUESTION_WORDS.values():
            for keyword in keywords:
                text = text.replace(keyword, '')
        
        # Берём первые несколько слов как тему
        words = text.split()
        if words:
            return ' '.join(words[:5])
        
        return 'неизвестно'

    def _is_informational_request(self, text: str) -> bool:
        """Проверить, является ли запрос информационным"""
        return any(phrase in text for phrase in self.INFO_PHRASES)

    def _get_greeting_response(self, text: str) -> Optional[str]:
        """Вернуть дружелюбный ответ для приветствий и простого общения"""
        normalized = text.strip().lower()
        # Убрать пунктуацию для более гибкого совпадения
        normalized_no_punct = re.sub(r'[!?.,:;]+$', '', normalized)
        
        for greeting, response in self.GREETING_RESPONSES.items():
            # Проверка точного совпадения (с удалением пунктуации в конце)
            if normalized_no_punct == greeting:
                return response
            # Проверка совпадения в начале (например "привет, Scott")
            if (normalized.startswith(greeting + ' ') or 
                normalized.startswith(greeting + ',') or
                normalized_no_punct.startswith(greeting + ' ') or
                normalized_no_punct.startswith(greeting + ',')):
                return response
        
        if normalized.startswith('как дела') or normalized.startswith('как ты'):
            return 'У меня всё отлично! А у тебя?'
        return None
    
    def _is_russian(self, text: str) -> bool:
        """Проверить русский язык"""
        return any('\u0400' <= char <= '\u04FF' for char in text)
    
    # ============= ОБРАБОТЧИКИ ВСТРОЕННЫХ ВОПРОСОВ =============
    
    def get_current_time(self, question: Question) -> str:
        """Текущее время"""
        now = datetime.now()
        time_str = now.strftime("%H:%M:%S")
        
        if question.context.get('language') == 'ru':
            return f"Сейчас {now.strftime('%H:%M')} и {now.strftime('%S')} секунд."
        else:
            return f"It's currently {time_str}."
    
    def get_current_date(self, question: Question) -> str:
        """Текущая дата"""
        now = datetime.now()
        
        if question.context.get('language') == 'ru':
            days = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье']
            months = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
                     'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
            day_name = days[now.weekday()]
            month_name = months[now.month - 1]
            return f"Сегодня {day_name}, {now.day} {month_name} {now.year} года."
        else:
            return now.strftime("%A, %B %d, %Y")
    
    def get_cpu_info(self, question: Question) -> str:
        """Информация о CPU"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            
            if question.context.get('language') == 'ru':
                return f"Использование процессора: {cpu_percent}%. Количество ядер: {cpu_count}."
            else:
                return f"CPU usage: {cpu_percent}%. Number of cores: {cpu_count}."
        except:
            return "Не удалось получить информацию о процессоре."
    
    def get_ram_info(self, question: Question) -> str:
        """Информация о RAM"""
        try:
            ram = psutil.virtual_memory()
            used_gb = ram.used / (1024**3)
            total_gb = ram.total / (1024**3)
            percent = ram.percent
            
            if question.context.get('language') == 'ru':
                return f"Памяти используется {used_gb:.1f} ГБ из {total_gb:.1f} ГБ ({percent}%)."
            else:
                return f"RAM usage: {used_gb:.1f} GB out of {total_gb:.1f} GB ({percent}%)."
        except:
            return "Не удалось получить информацию о памяти."
    
    def get_disk_info(self, question: Question) -> str:
        """Информация о диске"""
        try:
            disk = psutil.disk_usage('/')
            free_gb = disk.free / (1024**3)
            total_gb = disk.total / (1024**3)
            percent = disk.percent
            
            if question.context.get('language') == 'ru':
                return f"На диске свободно {free_gb:.1f} ГБ из {total_gb:.1f} ГБ. Занято {percent}%."
            else:
                return f"Free space: {free_gb:.1f} GB out of {total_gb:.1f} GB. Used: {percent}%."
        except:
            return "Не удалось получить информацию о диске."
    
    def get_os_info(self, question: Question) -> str:
        """Информация об ОС"""
        try:
            system = platform.system()
            release = platform.release()
            version = platform.version()
            
            if question.context.get('language') == 'ru':
                os_names = {
                    'Windows': 'Виндовс',
                    'Linux': 'Линукс',
                    'Darwin': 'macOS'
                }
                return f"Операционная система: {os_names.get(system, system)} {release}."
            else:
                return f"Operating System: {system} {release}"
        except:
            return "Не удалось определить ОС."
    
    def get_pc_name(self, question: Question) -> str:
        """Имя компьютера"""
        try:
            hostname = platform.node()
            if question.context.get('language') == 'ru':
                return f"Имя компьютера: {hostname}"
            else:
                return f"Computer name: {hostname}"
        except:
            return "Не удалось определить имя компьютера."
    
    def get_user_name(self, question: Question) -> str:
        """Имя пользователя"""
        try:
            import getpass
            username = getpass.getuser()
            if question.context.get('language') == 'ru':
                return f"Текущий пользователь: {username}"
            else:
                return f"Current user: {username}"
        except:
            return "Не удалось определить пользователя."
    
    def get_abilities(self, question: Question) -> str:
        """Возможности Scott AI"""
        abilities = [
            "Открывать приложения (Chrome, VS Code, Notepad и т.д.)",
            "Выполнять команды Windows",
            "Создавать и управлять файлами",
            "Получать информацию о курсах валют",
            "Искать информацию в интернете",
            "Отвечать на вопросы о системе",
            "Управлять окнами и процессами",
        ]
        
        if question.context.get('language') == 'ru':
            header = "Мои основные возможности:\n"
            return header + "\n".join(f"• {a}" for a in abilities)
        else:
            header = "My main capabilities:\n"
            return header + "\n".join(f"• {a}" for a in abilities)
    
    def get_version(self, question: Question) -> str:
        """Версия Scott AI"""
        version = "2.0"
        if question.context.get('language') == 'ru':
            return f"Scott AI версия {version}. Полностью готов к работе! 🚀"
        else:
            return f"Scott AI version {version}. Fully ready to work! 🚀"


def get_question_answerer() -> QuestionAnswerer:
    """Factory функция"""
    return QuestionAnswerer()
