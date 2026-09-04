"""
Интеллектуальный ИИ-ассистент на базе Groq LLM API (быстрый!) + OpenAI fallback
Полнофункциональный ChatGPT-подобный ассистент с памятью и контекстом
"""

import os
import json
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from pathlib import Path
import importlib
try:
    import httpx
except ImportError:
    httpx = None
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# DeepSeek support
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# Попробуем импортировать Groq
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    print("⚠️ Groq не установлен, используем OpenAI")


# Статические каталоги моделей — только для провайдеров, где нельзя дёшево и
# надёжно получить актуальный список чат-моделей живым запросом (у OpenAI
# models.list() возвращает сотни строк вперемешку с embeddings/whisper/dall-e;
# у DeepSeek список стабилен и мал). Для Groq список получаем НЕ отсюда, а
# живым запросом (см. list_groq_models) — однажды уже ловили баг с тем, что
# захардкоженная модель Groq оказалась снята с поддержки (llama-3.3-70b-versatile).
STATIC_PROVIDER_MODELS = {
    "OpenAI": [
        {"id": "gpt-4o", "note": "Лучшее качество и мультимодальность, дороже"},
        {"id": "gpt-4o-mini", "note": "Быстрее и дешевле gpt-4o, качество чуть ниже"},
        {"id": "gpt-4-turbo", "note": "Предыдущее поколение, тоже сильное"},
        {"id": "gpt-3.5-turbo", "note": "Самый дешёвый и быстрый, попроще"},
    ],
    "DeepSeek": [
        {"id": "deepseek-chat", "note": "Основная модель — быстрая, недорогая"},
        {"id": "deepseek-reasoner", "note": "С цепочкой рассуждений — сильнее в логике/математике, медленнее"},
    ],
}

AI_CONFIG_PATH = Path("data/ai_config.json")


def list_groq_models(api_key: str) -> List[Dict]:
    """Живой список чат-моделей Groq (исключая whisper/prompt-guard/tts — не для чата)."""
    if not GROQ_AVAILABLE:
        return []
    try:
        client = Groq(api_key=api_key)
        models = client.models.list()
        excluded_markers = ("whisper", "prompt-guard", "orpheus", "guard")
        return [
            {"id": m.id, "note": f"({getattr(m, 'owned_by', '') or 'Groq'})"}
            for m in models.data
            if not any(marker in m.id.lower() for marker in excluded_markers)
        ]
    except Exception as e:
        print(f"⚠️ Не удалось получить список моделей Groq: {e}")
        return []


class ConversationMemory:
    """Управление памятью разговоров"""
    
    def __init__(self, max_history: int = 20):
        self.max_history = max_history
        self.conversations = []
        self.context_file = Path("data/conversations.jsonl")
        self._load_history()
    
    def _load_history(self):
        """Загрузить историю разговоров"""
        if self.context_file.exists():
            try:
                with open(self.context_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    self.conversations = [json.loads(line) for line in lines[-self.max_history:]]
                print(f"📚 Загружено {len(self.conversations)} сообщений истории")
            except Exception as e:
                print(f"⚠️ Ошибка загрузки истории: {e}")
                self.conversations = []
    
    def add_message(self, role: str, content: str):
        """Добавить сообщение в память"""
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        self.conversations.append(message)
        
        # Ограничиваем историю
        if len(self.conversations) > self.max_history:
            self.conversations = self.conversations[-self.max_history:]
        
        self._save_message(message)
    
    def _save_message(self, message: Dict):
        """Сохранить сообщение в файл"""
        try:
            self.context_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.context_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(message, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"⚠️ Ошибка сохранения: {e}")
    
    def get_context(self) -> List[Dict]:
        """Получить контекст для отправки в API"""
        return [{"role": msg["role"], "content": msg["content"]} 
                for msg in self.conversations]
    
    def clear(self):
        """Очистить память"""
        self.conversations = []


class IntelligentAnswerer:
    """Полнофункциональный ИИ-ассистент на Groq + OpenAI fallback"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Инициализация ИИ-ассистента

        Args:
            api_key: Groq API ключ (если None, берется из env GROQ_API_KEY)
        """
        # Параметры модели (устанавливаем ДО проверки API)
        self.model = "openai/gpt-oss-120b"  # Groq активная модель (llama-3.3 снята с поддержки Groq)
        self.temperature = 0.7
        self.max_tokens = 1000

        self.client = None
        self.api_provider = None
        self.enabled = False

        # Ключи из .env — используются, если пользователь не задал свой через /ai/configure
        self.env_keys = {
            "Groq": os.getenv("GROQ_API_KEY"),
            "DeepSeek": os.getenv("DEEPSEEK_API_KEY"),
            "OpenAI": os.getenv("OPENAI_API_KEY"),
        }
        # Ключи, явно введённые пользователем через Настройки (в приоритете над .env)
        self.custom_keys: Dict[str, str] = {}

        connected = False
        saved = self._load_saved_config()
        if saved and saved.get("provider") and saved.get("model"):
            if saved.get("api_key"):
                self.custom_keys[saved["provider"]] = saved["api_key"]
            resolved_key = self.custom_keys.get(saved["provider"]) or self.env_keys.get(saved["provider"])
            connected = self._connect_provider(saved["provider"], saved["model"], resolved_key)
            if connected:
                print(f"✅ Восстановлена сохранённая конфигурация ИИ: {saved['provider']} / {saved['model']}")
            else:
                print(f"⚠️ Не удалось восстановить сохранённую конфигурацию ИИ ({saved['provider']}), пробую .env по умолчанию")

        # Приоритет по умолчанию (если нет сохранённой конфигурации или она не сработала):
        # Groq → DeepSeek → OpenAI
        if not connected and GROQ_AVAILABLE and self.env_keys["Groq"]:
            connected = self._connect_provider("Groq", "openai/gpt-oss-120b", self.env_keys["Groq"])

        if not connected and self.env_keys["DeepSeek"] and REQUESTS_AVAILABLE:
            connected = self._connect_provider("DeepSeek", "deepseek-chat", self.env_keys["DeepSeek"])

        if not connected and self.env_keys["OpenAI"] and OPENAI_AVAILABLE:
            connected = self._connect_provider("OpenAI", "gpt-3.5-turbo", self.env_keys["OpenAI"])

        # Если ничего не работает
        if not self.enabled:
            print("⚠️ Ни Groq, DeepSeek ни OpenAI не доступны!")
            print("   Используем fallback ответы для базовых вопросов")

        # Память разговоров
        # Уменьшено с 20 до 6: аккаунт Groq ограничен 8000 TPM (tokens per minute),
        # и с полной историей запросы регулярно упирались в 413 Request too large.
        self.memory = ConversationMemory(max_history=6)
        
        # Системный промпт на русском
        self.system_prompt = """Ты помощник Scott AI - умный ИИ-ассистент.
Ты обучен работать со многими темами: программирование, наука, история, искусство, математика и многое другое.
Ты помогаешь пользователю ответить на вопросы, объясняешь сложные концепции, решаешь задачи.

ПРАВИЛА:
1. Отвечай на русском языке, если пользователь на русском
2. Будь точен и полезен
3. Если не знаешь - скажи честно
4. Используй примеры и аналогии для объяснения
5. Помни контекст предыдущих разговоров
6. Будь дружелюбен и профессионален

Тебя зовут Scott AI, ты персональный ИИ-ассистент."""
    
    def _test_connection_groq(self):
        """Проверить подключение к Groq API"""
        try:
            print("🧪 Тестирование Groq API...")
            # Простой тест - получить список моделей
            models = self.client.models.list()
            print(f"✅ Groq API работает!")
        except Exception as e:
            print(f"⚠️ Ошибка тестирования Groq: {e}")
            self.enabled = False
    
    def _test_connection_openai(self):
        """Проверить подключение к OpenAI API"""
        try:
            print("🧪 Тестирование OpenAI API...")
            # Простой тест - получить список моделей
            response = self.client.models.list()
            print(f"✅ OpenAI API работает!")
        except Exception as e:
            print(f"⚠️ Ошибка тестирования OpenAI: {e}")
            self.enabled = False

    def _connect_provider(self, provider: str, model: str, api_key: Optional[str]) -> bool:
        """Подключиться к конкретному провайдеру с конкретной моделью и ключом.
        Общая точка входа и для стандартной инициализации, и для ручного
        переключения через /ai/configure — раньше три провайдера подключались
        тремя копипастами кода в __init__."""
        if not api_key:
            return False
        try:
            if provider == "Groq":
                if not GROQ_AVAILABLE:
                    return False
                self.client = Groq(api_key=api_key)
                self.enabled = True
                self.api_provider = "Groq"
                self.model = model
                print(f"✅ Groq API подключен (модель: {self.model})")
                self._test_connection_groq()
            elif provider == "DeepSeek":
                if not REQUESTS_AVAILABLE:
                    return False
                self.client = {"api_key": api_key, "base_url": "https://api.deepseek.com"}
                self.enabled = True
                self.api_provider = "DeepSeek"
                self.model = model
                print(f"✅ DeepSeek API подключен (модель: {self.model})")
            elif provider == "OpenAI":
                if not OPENAI_AVAILABLE:
                    return False
                import openai as openai_client
                if httpx is None:
                    raise ImportError("httpx is required для OpenAI integration")
                http_client = httpx.Client()
                self.client = openai_client.OpenAI(api_key=api_key, http_client=http_client)
                self.enabled = True
                self.api_provider = "OpenAI"
                self.model = model
                print(f"✅ OpenAI API подключен (модель: {self.model})")
                self._test_connection_openai()
            else:
                print(f"⚠️ Неизвестный провайдер: {provider}")
                return False

            return self.enabled
        except Exception as e:
            print(f"⚠️ Ошибка подключения {provider}: {e}")
            self.client = None
            self.api_provider = None
            self.enabled = False
            return False

    def _load_saved_config(self) -> Optional[Dict]:
        """Загрузить сохранённый выбор провайдера/модели/ключа (см. /ai/configure)."""
        if AI_CONFIG_PATH.exists():
            try:
                with open(AI_CONFIG_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Не удалось прочитать сохранённую конфигурацию ИИ: {e}")
        return None

    def _save_config(self, provider: str, model: str, api_key: Optional[str]) -> None:
        """Сохранить текущий выбор провайдера/модели/ключа на диск, чтобы он пережил перезапуск backend."""
        try:
            AI_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = {"provider": provider, "model": model}
            if api_key:
                data["api_key"] = api_key
            with open(AI_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ Не удалось сохранить конфигурацию ИИ: {e}")

    def configure(self, provider: str, model: str, api_key: Optional[str] = None) -> Dict:
        """
        Переключить активного провайдера и/или модель — с собственным API-ключом
        пользователя либо переиспользуя уже известный (ранее введённый или из .env).
        """
        resolved_key = api_key or self.custom_keys.get(provider) or self.env_keys.get(provider)
        if not resolved_key:
            return {"success": False, "error": f"Нет API-ключа для {provider} — укажите свой ключ"}

        previous = (self.api_provider, self.model, self.client, self.enabled)
        if not self._connect_provider(provider, model, resolved_key):
            # Откатываемся к прежнему рабочему состоянию, а не остаёмся сломанными
            self.api_provider, self.model, self.client, self.enabled = previous
            return {"success": False, "error": f"Не удалось подключиться к {provider} (модель «{model}») с этим ключом"}

        if api_key:
            self.custom_keys[provider] = api_key
        self._save_config(provider, model, self.custom_keys.get(provider))
        return {"success": True, "provider": provider, "model": model}

    def get_available_providers(self) -> List[Dict]:
        """Список провайдеров с их моделями и статусом — для выбора в Настройках."""
        providers = []

        groq_key = self.custom_keys.get("Groq") or self.env_keys.get("Groq")
        providers.append({
            "id": "Groq",
            "note": "Очень быстрые ответы, есть бесплатный тариф",
            "configured": bool(groq_key) and GROQ_AVAILABLE,
            "models": list_groq_models(groq_key) if (groq_key and GROQ_AVAILABLE) else [],
        })

        provider_notes = {
            "OpenAI": "Высокое качество ответов, платно",
            "DeepSeek": "Сильна в логике/математике, недорого",
        }
        for provider_id, models in STATIC_PROVIDER_MODELS.items():
            key = self.custom_keys.get(provider_id) or self.env_keys.get(provider_id)
            providers.append({
                "id": provider_id,
                "note": provider_notes.get(provider_id, ""),
                "configured": bool(key),
                "models": models,
            })

        return providers

    def answer(self, text: str, use_memory: bool = True) -> Tuple[str, bool]:
        """
        Получить ответ от ИИ (Groq или OpenAI)
        
        Args:
            text: Текст вопроса
            use_memory: Использовать ли контекст разговора
        
        Returns:
            (ответ, успех)
        """
        if not self.enabled or not self.client:
            return "❌ ИИ-ассистент недоступен. Используйте fallback ответы", False
        
        try:
            # Добавляем пользовательское сообщение в память
            self.memory.add_message("user", text)
            
            # Получаем контекст разговора
            messages = [{"role": "system", "content": self.system_prompt}]
            if use_memory:
                messages.extend(self.memory.get_context())
            else:
                messages.append({"role": "user", "content": text})
            
            # Используем DeepSeek если доступен
            if self.api_provider == "DeepSeek":
                print(f"🔷 DeepSeek API запрос ({self.model})...")
                response = requests.post(
                    "https://api.deepseek.com/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.client['api_key']}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": self.temperature,
                        "max_tokens": self.max_tokens,
                    },
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()
                answer = data["choices"][0]["message"]["content"].strip()
                print(f"✅ DeepSeek ответ получен ({len(answer)} символов)")
            
            # Используем Groq если доступен
            elif self.api_provider == "Groq":
                print(f"⚡ Groq API запрос ({self.model})...")
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens
                )
                answer = response.choices[0].message.content.strip()
                print(f"✅ Groq ответ получен ({len(answer)} символов)")
            
            # Fallback на OpenAI
            elif self.api_provider == "OpenAI":
                print(f"🤖 OpenAI API запрос ({self.model})...")
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    top_p=0.95,
                    presence_penalty=0.0,
                    frequency_penalty=0.0
                )
                answer = response.choices[0].message.content.strip()
                print(f"✅ OpenAI ответ получен ({len(answer)} символов)")
            
            else:
                return "❌ Неизвестный провайдер API", False
            
            # Сохраняем ответ в память
            self.memory.add_message("assistant", answer)
            return answer, True
        
        except Exception as e:
            error_msg = f"❌ Ошибка API: {str(e)}"
            print(error_msg)
            return error_msg, False
    
    def answer_question(self, question: str) -> str:
        """
        Быстрый метод получить ответ (alias для answer)
        Поддерживает fallback режим без OpenAI API
        
        Args:
            question: Вопрос пользователя
            
        Returns:
            Ответ на вопрос (str)
        """
        if not self.enabled or not self.client:
            # Fallback режим - простые ответы без API
            return self._fallback_answer(question)
        
        answer, success = self.answer(question, use_memory=True)
        return answer
    
    def _fallback_answer(self, question: str) -> str:
        """
        Простые ответы без OpenAI API
        Используется когда OPENAI_API_KEY не установлена
        """
        q_lower = question.lower().strip()
        
        # Простые ответы на базовые вопросы
        responses = {
            # Приветствия
            'привет': 'Привет! Я Scott AI. Как дела? Чем я могу помочь?',
            'здравствуй': 'Здравствуйте! Это Scott AI. Готов помочь!',
            'hi': 'Hello! I am Scott AI, your intelligent assistant!',
            
            # Время
            'время': f'Текущее время: {datetime.now().strftime("%H:%M:%S")}',
            'сколько времени': f'Время: {datetime.now().strftime("%H:%M:%S")}',
            'который час': f'Сейчас {datetime.now().strftime("%H:%M")}',
            
            # Дата
            'дата': f'Сегодняшняя дата: {datetime.now().strftime("%d.%m.%Y")}',
            'какая сегодня дата': f'Дата: {datetime.now().strftime("%d.%m.%Y")}',
            'какой сегодня день': f'Сегодня {datetime.now().strftime("%A, %d %B %Y")}',
            
            # О возможностях
            'что ты можешь': 'Я могу: отвечать на вопросы, показывать время/дату, помогать с информацией, выполнять команды. Установите OPENAI_API_KEY для расширенной функциональности.',
            'возможности': 'Мои возможности: текстовые вопросы, время, дату, голосовые команды, настройки. Нужен OPENAI_API_KEY для полного ИИ.',
            'help': 'I can help with questions, show time/date, execute commands. Set OPENAI_API_KEY for advanced AI.',
        }
        
        # Проверяем совпадения
        for key, response in responses.items():
            if key in q_lower:
                return response
        
        # Дополнительные статические ответы на базовые вопросы
        if 'что такое python' in q_lower or 'что такое py' in q_lower:
            return ('Python — это высокоуровневый язык программирования общего назначения. '
                    'Он прост в изучении, поддерживает объектно-ориентированное и функциональное '
                    'программирование, и используется для веб-разработки, анализа данных, автоматизации и науки.')
        if 'из чего состоит атом' in q_lower or 'что такое атом' in q_lower:
            return ('Атом состоит из центрального ядра, в котором находятся протоны и нейтроны, '
                    'и облака электронов, вращающихся вокруг ядра. Протоны заряжены положительно, '
                    'нейтроны не имеют заряда, а электроны заряжены отрицательно.')

        # Если не найдено, возвращаем общий ответ
        return f'Спасибо за вопрос: "{question}". Для полной функциональности ИИ, пожалуйста, установите переменную окружения OPENAI_API_KEY. А сейчас я могу помочь с основными командами: время, дату, информацию.'

    def answer_with_analysis(self, text: str) -> Dict:
        """
        Получить ответ с анализом типа вопроса
        
        Returns:
            {
                "answer": str,
                "success": bool,
                "type": "definition|explanation|analysis|creative|etc",
                "confidence": 0.0-1.0
            }
        """
        answer, success = self.answer(text)
        
        return {
            "answer": answer,
            "success": success,
            "type": self._detect_question_type(text),
            "confidence": 0.95 if success else 0.0
        }
    
    def _detect_question_type(self, text: str) -> str:
        """Определить тип вопроса"""
        text_lower = text.lower()
        
        if any(word in text_lower for word in ['что такое', 'что это', 'кто такой', 'кто это']):
            return "definition"
        elif any(word in text_lower for word in ['как', 'каким образом', 'объясни']):
            return "explanation"
        elif any(word in text_lower for word in ['почему', 'зачем', 'причин']):
            return "reasoning"
        elif any(word in text_lower for word in ['сравни', 'разница', 'отличие']):
            return "comparison"
        elif any(word in text_lower for word in ['напиши', 'создай', 'придумай', 'сочини']):
            return "creative"
        elif any(word in text_lower for word in ['докажи', 'проверь', 'верно ли']):
            return "analysis"
        else:
            return "general"
    
    def set_model(self, model: str):
        """Изменить модель (gpt-3.5-turbo или gpt-4)"""
        self.model = model
        print(f"🔄 Модель изменена на: {model}")
    
    def set_temperature(self, temp: float):
        """Изменить креативность (0.0-1.0)"""
        self.temperature = max(0.0, min(1.0, temp))
        print(f"🔄 Креативность: {self.temperature}")
    
    def clear_memory(self):
        """Очистить память разговоров"""
        self.memory.clear()
        print("🗑️ Память очищена")
    
    def get_stats(self) -> Dict:
        """Получить статистику"""
        return {
            "enabled": self.enabled,
            "api_connected": self.enabled,
            "model": self.model,
            "memory_messages": len(self.memory.conversations),
            "max_history": self.memory.max_history
        }


# Глобальный экземпляр
intelligent_answerer = None


def init_intelligent_answerer():
    """Инициализировать глобальный ИИ-ассистент"""
    global intelligent_answerer
    try:
        print("✨ Инициализирую IntelligentAnswerer...")
        intelligent_answerer = IntelligentAnswerer()
        print(f"✅ IntelligentAnswerer инициализирован (enabled={intelligent_answerer.enabled})")
        return intelligent_answerer
    except Exception as e:
        print(f"❌ Ошибка инициализации IntelligentAnswerer: {e}")
        import traceback
        traceback.print_exc()
        intelligent_answerer = None
        return None


def get_intelligent_answerer() -> Optional[IntelligentAnswerer]:
    """Получить глобальный ИИ-ассистент"""
    global intelligent_answerer
    if intelligent_answerer is None:
        init_intelligent_answerer()
    return intelligent_answerer
