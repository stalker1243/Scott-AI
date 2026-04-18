"""Движок обработки вопросов через LLM."""
from dataclasses import dataclass
from typing import Optional
import os
import sys
from .question_analyzer import QuestionAnalyzer, QuestionAnalysis

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Импортируем базу знаний (опционально)
try:
    from ..knowledge_base import KnowledgeBase
    KNOWLEDGE_AVAILABLE = True
except ImportError:
    try:
        from knowledge_base import KnowledgeBase
        KNOWLEDGE_AVAILABLE = True
    except ImportError:
        KNOWLEDGE_AVAILABLE = False


@dataclass
class LlmConfig:
    """Конфигурация LLM движка."""
    provider: str = "dummy"  # "openai", "yandexgpt", "ollama", "dummy" (по умолчанию - заглушка)
    model: str = "qwen2.5:7b"  # для Ollama: "qwen2.5:7b", "llama3.2", "mistral" и др. Для OpenAI: "gpt-3.5-turbo"
    api_key: Optional[str] = None
    temperature: float = 0.5   # ещё чуть ниже для более стабильных и быстрых ответов
    max_tokens: int = 256      # короче ответы -> быстрее генерация
    ollama_base_url: str = "http://localhost:11434"  # URL Ollama сервера


class LlmEngine:
    """
    Движок обработки вопросов через LLM.
    Поддерживает разные провайдеры: OpenAI API, локальные модели, заглушка.
    """

    def __init__(self, config: Optional[LlmConfig] = None, knowledge_base: Optional['KnowledgeBase'] = None):
        self.config = config or LlmConfig()
        self._client = None
        self.analyzer = QuestionAnalyzer()
        self.knowledge_base = knowledge_base
        if not self.knowledge_base and KNOWLEDGE_AVAILABLE:
            try:
                try:
                    from ..knowledge_base import get_default_knowledge_base
                except ImportError:
                    from knowledge_base import get_default_knowledge_base
                self.knowledge_base = get_default_knowledge_base()
            except:
                pass

    def _init_client(self):
        """Инициализация клиента для выбранного провайдера."""
        if self._client is not None:
            return

        if self.config.provider == "openai":
            try:
                from openai import OpenAI
                # Пробуем загрузить из .env файла (если есть python-dotenv)
                try:
                    from dotenv import load_dotenv
                    load_dotenv()
                except ImportError:
                    pass  # python-dotenv не установлен, пропускаем
                
                api_key = self.config.api_key or os.getenv("OPENAI_API_KEY")
                if api_key:
                    self._client = OpenAI(api_key=api_key)
                    print("✅ OpenAI клиент инициализирован")
                else:
                    print("⚠️  OPENAI_API_KEY не найден. Используется заглушка.")
                    print("💡 Подсказка: установите переменную окружения OPENAI_API_KEY или создайте файл .env")
                    self._client = "dummy"
            except ImportError:
                print("⚠️  openai не установлен. Используется заглушка.")
                print("💡 Установите: pip install openai")
                self._client = "dummy"

        elif self.config.provider == "ollama":
            # Ollama - локальный LLM, работает через HTTP API
            try:
                import requests
                # Проверяем доступность Ollama сервера
                try:
                    response = requests.get(f"{self.config.ollama_base_url}/api/tags", timeout=2)
                    if response.status_code == 200:
                        self._client = "ollama"
                        print("✅ Ollama сервер найден")
                    else:
                        print("⚠️  Ollama сервер не отвечает. Используется заглушка.")
                        self._client = "dummy"
                except (requests.exceptions.RequestException, requests.exceptions.Timeout):
                    print("⚠️  Ollama сервер не запущен. Запустите Ollama или используйте заглушку.")
                    print("💡 Установите Ollama: https://ollama.ai/download")
                    print("💡 Запустите модель: ollama run llama3.2")
                    self._client = "dummy"
            except ImportError:
                print("⚠️  requests не установлен. Установите: pip install requests")
                self._client = "dummy"
        
        elif self.config.provider == "dummy":
            # Заглушка - работает без API, отвечает на базовые вопросы
            self._client = "dummy"

    def answer(self, question: str, context: Optional[str] = None) -> str:
        """
        Получить ответ на вопрос.
        
        Args:
            question: Вопрос пользователя
            context: Дополнительный контекст (опционально)
            
        Returns:
            Ответ модели
        """
        self._init_client()
        
        # Анализируем вопрос для улучшения ответа
        analysis = self.analyzer.analyze(question)

        # Определяем язык вопроса (ru / en) для более корректного стиля ответа
        language = self._detect_language(question)
        
        # Получаем релевантные знания из базы знаний
        knowledge_context = ""
        if self.knowledge_base:
            knowledge_context = self.knowledge_base.get_context_for_question(question)
            if knowledge_context:
                context = f"{context}\n\n{knowledge_context}" if context else knowledge_context
        
        # Для математических вопросов пробуем вычислить ответ
        if analysis.requires_calculation and analysis.category == "math":
            calculated_answer = self._try_calculate(question)
            if calculated_answer:
                return calculated_answer

        if self._client == "dummy":
            # Умная заглушка с опорой на базу знаний
            return self._dummy_answer(question, analysis, context)

        if self.config.provider == "openai":
            return self._openai_answer(question, context, analysis, language)
        
        if self.config.provider == "ollama" and self._client == "ollama":
            return self._ollama_answer(question, context, analysis, language)

        return "Неизвестный провайдер LLM."

    def _dummy_answer(self, question: str, analysis: QuestionAnalysis, context: Optional[str] = None) -> str:
        """Простая заглушка с базовыми правилами."""
        question_lower = question.lower().strip()

        # Если есть релевантный контекст из базы знаний — используем его в ответе.
        if context and "Релевантные знания" in context:
            lines = [ln.strip() for ln in context.splitlines() if ln.strip()]
            facts = [ln.split(". ", 1)[1] if ". " in ln else ln for ln in lines if ln[:1].isdigit()]
            if facts:
                main = facts[0]
                extra = f" {facts[1]}" if len(facts) > 1 else ""
                return f"{main}{extra}"

        # Простые правила для демонстрации
        if any(word in question_lower for word in ["привет", "здравствуй", "hello", "hi"]):
            return "Привет! Чем могу помочь?"

        if any(word in question_lower for word in ["как дела", "как ты", "how are you"]):
            return "У меня всё отлично! Готов отвечать на твои вопросы."

        if any(word in question_lower for word in ["что ты", "кто ты", "what are you"]):
            return "Я нейросеть для озвучки мультфильмов и фильмов. Могу отвечать на вопросы и озвучивать ответы."

        if any(word in question_lower for word in ["время", "который час", "what time"]):
            from datetime import datetime
            return f"Сейчас {datetime.now().strftime('%H:%M:%S')}."

        # Математические вопросы
        if analysis.category == "math":
            calculated = self._try_calculate(question)
            if calculated:
                return calculated
            return "Это математический вопрос. Для точных вычислений подключите LLM (Ollama или другой)."
        
        # Научные вопросы
        if analysis.category == "science":
            return "Это научный вопрос. Для подробного ответа подключите LLM модель (Ollama работает отлично для таких вопросов)."
        
        if "?" in question or any(word in question_lower for word in ["почему", "зачем", "why"]):
            return "Это интересный вопрос! Для полного ответа подключите реальную LLM модель (Ollama или другую)."

        # Дефолтный ответ
        return f"Я понял твой вопрос: '{question}'. Это интересно! Для более детальных ответов подключите LLM (Ollama работает отлично)."

    def _detect_language(self, text: str) -> str:
        """
        Простейшее определение языка вопроса.
        Возвращает 'ru' если есть кириллица, 'en' если только латиница, иначе 'ru' по умолчанию.
        """
        has_cyrillic = any("а" <= ch.lower() <= "я" for ch in text)
        has_latin = any("a" <= ch.lower() <= "z" for ch in text)

        if has_cyrillic and not has_latin:
            return "ru"
        if has_latin and not has_cyrillic:
            return "en"
        # Смешанный текст – по умолчанию считаем, что пользователь говорит по‑русски
        return "ru"

    def _get_system_prompt(self, analysis: QuestionAnalysis, language: str = "ru") -> str:
        """
        Генерирует системный промпт на основе анализа вопроса и языка.

        Цели:
        - Красивый, структурированный ответ
        - Грамотный русский / английский
        - Эмодзи и знаки допускаются в тексте для пользователя,
          но текст должен оставаться чистым и понятным для озвучки.
        """
        language = (language or "ru").lower()

        if language == "en":
            # Базовый стиль на английском
            base_prompt = (
                "You are Scott, a calm, intelligent voice assistant. "
                "Always answer in clear, natural English. "
                "You may use emojis occasionally to express emotion, but do not overuse them. "
                "Avoid markdown and code blocks. Do not describe punctuation marks explicitly, "
                "just write normal sentences as they should be spoken. "
            )

            if analysis.category == "math":
                base_prompt += (
                    "You are an experienced math teacher. Explain solutions step by step, "
                    "but keep them concise and understandable. "
                )
            elif analysis.category == "science":
                base_prompt += (
                    "You are a science explainer. Give accurate scientific answers, "
                    "using simple language and short examples. "
                )
            elif analysis.category == "simple":
                base_prompt += "Give short, friendly answers. "
            else:  # general
                base_prompt += (
                    "Give structured, informative answers with short paragraphs. "
                )

            if analysis.difficulty == "hard":
                base_prompt += "For hard questions give a detailed explanation in several short paragraphs. "
            elif analysis.difficulty == "medium":
                base_prompt += "For medium questions give a clear answer with one or two simple examples. "

        else:
            # Базовый стиль на русском
            base_prompt = (
                "Ты Скотт — спокойный и умный голосовой ассистент. "
                "Отвечай всегда на грамотном русском языке, естественно и человеческим стилем. "
                "Не используй эмодзи и не добавляй лишние символы. "
                "Избегай markdown-разметки и кода. Не нужно описывать или называть вслух знаки препинания — "
                "формируй обычные фразы, которые приятно слушать как естественную речь. "
                "Пиши короткими предложениями. Не используй англицизмы без необходимости. "
                "Если встречаются аббревиатуры (например, «и т.д.»), лучше раскрывай их словами. "
                "Старайся использовать «ё» там, где она нужна (например: «всё», «ещё»), чтобы озвучка была точнее. "
            )

            if analysis.category == "math":
                base_prompt += (
                    "Ты опытный учитель математики. Отвечай чётко и по шагам: сначала короткий ответ, "
                    "затем при необходимости краткое объяснение. "
                    "Если нужно, оформляй решение как: «Шаг 1…», «Шаг 2…». "
                )
            elif analysis.category == "science":
                base_prompt += (
                    "Ты учёный-объяснитель. Отвечай научно обоснованно, но простым языком, "
                    "приводи понятные примеры из жизни. "
                )
            elif analysis.category == "simple":
                base_prompt += "Отвечай кратко, дружелюбно и по делу. "
            else:  # general
                base_prompt += (
                    "Отвечай развёрнуто и информативно, используя короткие абзацы. "
                )

            if analysis.difficulty == "hard":
                base_prompt += (
                    "Это сложный вопрос — дай подробный, но хорошо структурированный ответ "
                    "из нескольких коротких абзацев, избегая длинных запутанных предложений. "
                )
            elif analysis.difficulty == "medium":
                base_prompt += (
                    "Это вопрос средней сложности — дай понятный ответ с одним-двумя простыми примерами. "
                )

        return base_prompt

    def _openai_answer(
        self,
        question: str,
        context: Optional[str] = None,
        analysis: Optional[QuestionAnalysis] = None,
        language: str = "ru",
    ) -> str:
        """Ответ через OpenAI API."""
        messages = []
        
        # Добавляем системный промпт на основе анализа
        system_prompt = self._get_system_prompt(analysis, language) if analysis else ""
        if context:
            system_prompt = f"{system_prompt}\nКонтекст: {context}" if system_prompt else f"Контекст: {context}"
        
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })
        
        messages.append({
            "role": "user",
            "content": question
        })

        response = self._client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

        return response.choices[0].message.content.strip()

    def _ollama_answer(
        self,
        question: str,
        context: Optional[str] = None,
        analysis: Optional[QuestionAnalysis] = None,
        language: str = "ru",
    ) -> str:
        """Ответ через Ollama API (локально)."""
        import requests
        
        # Формируем промпт с контекстом, если есть
        prompt = question
        if context:
            prompt = f"Контекст: {context}\n\nВопрос: {question}"
        
        # Используем API /api/chat для более естественного диалога
        messages = []
        
        # Добавляем системный промпт на основе анализа
        system_prompt = self._get_system_prompt(analysis, language) if analysis else ""
        if context:
            system_prompt = f"{system_prompt}\nКонтекст: {context}" if system_prompt else context
        
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })
        
        messages.append({
            "role": "user",
            "content": question
        })
        
        try:
            response = requests.post(
                f"{self.config.ollama_base_url}/api/chat",
                json={
                    "model": self.config.model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": self.config.temperature,
                        "num_predict": self.config.max_tokens,
                    }
                },
                timeout=60  # Ollama может работать медленно
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("message", {}).get("content", "").strip()
            else:
                error_msg = f"Ollama API ошибка: {response.status_code}"
                try:
                    error_detail = response.json().get("error", "")
                    if error_detail:
                        error_msg += f" - {error_detail}"
                except:
                    pass
                print(f"⚠️  {error_msg}")
                return f"Ошибка Ollama: {error_msg}"
        
        except requests.exceptions.Timeout:
            return "Ollama не ответил вовремя. Попробуйте ещё раз или используйте более быструю модель."
        except requests.exceptions.RequestException as e:
            return f"Ошибка подключения к Ollama: {str(e)}"


def get_default_llm_engine() -> LlmEngine:
    """Фабрика для получения LLM движка по умолчанию."""
    return LlmEngine()

