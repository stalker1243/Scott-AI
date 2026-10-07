"""
Интеллектуальный ИИ-ассистент на базе Groq LLM API (быстрый!) + OpenAI fallback
Полнофункциональный ChatGPT-подобный ассистент с памятью и контекстом
"""

import os
import json
import re
import time
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from pathlib import Path
import importlib
import tempfile
import copy
import threading
from collections import deque
try:
    from .storage import atomic_write_text
except ImportError:
    from storage import atomic_write_text
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
# Модели Groq на случай, когда ключа ещё нет. Живой список запрашивается у
# самого Groq, но для этого нужен ключ — а выбрать модель человек должен ДО
# того, как ключ применён. Здесь общедоступные модели бесплатного тарифа.
# Порядок важен: первая строка — то, что подставится человеку по умолчанию,
# поэтому здесь стоят модели, реально доступные на бесплатном тарифе. Список
# сверен с ответом Groq: названия вроде llama-3.3-70b, которых нет у обычного
# аккаунта, сюда попадать не должны — иначе первая же попытка упрётся в
# «модель недоступна».
GROQ_FALLBACK_MODELS = [
    {"id": "openai/gpt-oss-120b", "note": "Крупная модель, хорошо отвечает по-русски"},
    {"id": "openai/gpt-oss-20b", "note": "Та же линейка, легче и быстрее"},
    {"id": "groq/compound-mini", "note": "Быстрая, для простых вопросов"},
    {"id": "qwen/qwen3.8-27b", "note": "Альтернатива, если первые заняты лимитом"},
]

# Сколько ждать ответа модели. Дольше ждать бессмысленно: человек, задавший
# вопрос голосом, к этому времени уже решил, что его не услышали. Замеры до
# ограничения: среднее 7.3 с, худшие пять процентов — 29 с.
REQUEST_TIMEOUT_SECONDS = 25

# Сколько раз пробовать. Вторая попытка нужна ради лимита запросов: у
# бесплатного тарифа Groq он невелик, а отказ по нему — дело секунды.
MAX_ATTEMPTS = 2

# Пауза перед повтором, если сервис не назвал свою.
RETRY_PAUSE_SECONDS = 1.5


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
    # Здесь только то, в чём есть уверенность. Живой список Anthropic отдаёт
    # сам, и он всегда точнее: модели появляются и снимаются чаще, чем выходят
    # версии Scott.
    "Anthropic": [
        {"id": "claude-sonnet-5", "note": "Обычный выбор: сильная и не самая дорогая"},
        {"id": "claude-opus-5", "note": "Самая способная, дороже и медленнее"},
        {"id": "claude-haiku-4-5-20251001", "note": "Быстрая и дешёвая, для простого"},
    ],
    # У шлюза каталог живой по определению — здесь пусто не случайно: любой
    # статический список устареет раньше, чем человек дочитает его до конца.
    "OpenRouter": [
        {"id": "anthropic/claude-sonnet-5", "note": "Claude через шлюз"},
        {"id": "openai/gpt-4o", "note": "GPT через шлюз"},
        {"id": "google/gemini-2.0-flash-001", "note": "Gemini через шлюз"},
        {"id": "meta-llama/llama-3.3-70b-instruct", "note": "Llama через шлюз"},
    ],
}

# Шлюзы, у которых список моделей запрашивается живым запросом. У каждого свой
# адрес и свой способ назвать ключ.
ANTHROPIC_BASE = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2023-06-01"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"


def list_anthropic_models(api_key: str) -> List[Dict]:
    """
    Живой список моделей Claude.

    Anthropic отдаёт его одним запросом и без лишнего: там только модели для
    разговора, фильтровать нечего — в отличие от OpenAI, где в общий список
    попадают и распознавание речи, и рисование.
    """
    if not REQUESTS_AVAILABLE:
        return []

    try:
        response = requests.get(
            f"{ANTHROPIC_BASE}/models",
            headers={"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION},
            timeout=10,
        )
        response.raise_for_status()

        return [
            {"id": item["id"], "note": item.get("display_name", "") or "Anthropic"}
            for item in response.json().get("data", [])
            if item.get("id")
        ]
    except Exception as e:
        print(f"⚠️ Не удалось получить список моделей Anthropic: {e}")
        return []


def list_openrouter_models(api_key: str = "") -> List[Dict]:
    """
    Живой список моделей шлюза — сотни строк от разных поставщиков.

    Ключ здесь не обязателен: каталог у шлюза открытый, и показать его можно
    ещё до того, как человек ввёл ключ. Это ровно тот случай, ради которого
    статические каталоги и заводились, — только здесь он решается честно.

    Бесплатные модели вынесены наверх: с них разумно начинать знакомство, а в
    списке на сотни строк их иначе не найти.
    """
    if not REQUESTS_AVAILABLE:
        return []

    try:
        from .model_capabilities import capabilities
    except ImportError:
        from model_capabilities import capabilities

    try:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        response = requests.get(f"{OPENROUTER_BASE}/models", headers=headers, timeout=15)
        response.raise_for_status()

        модели = []
        for item in response.json().get("data", []):
            ident = item.get("id")
            if not ident:
                continue

            # Шлюз отдаёт не только разговорные модели: там же рисование,
            # музыка и распознавание речи. Для Scott годятся только те, что
            # принимают текст и отвечают текстом, — остальные в списке выбора
            # означали бы обещание, которое некому выполнить.
            modality = (item.get("architecture") or {}).get("modality", "")
            if modality and 'text' not in modality.split('->')[-1] and 'image' not in modality.split('->')[-1]:
                continue

            цена = (item.get("pricing") or {}).get("prompt")
            бесплатно = цена in ("0", 0, "0.0")

            try:
                from .model_capabilities import capabilities
            except ImportError:
                from model_capabilities import capabilities
            model_caps = capabilities('OpenRouter', ident, item.get('architecture') or {})
            модели.append({
                "id": ident,
                "note": item.get("name") or "OpenRouter",
                "free": бесплатно and not model_caps['image_generation'],
                "capabilities": model_caps,
            })

        # Dedicated image models are published in a separate catalog as well.
        # A failure there must still leave the text/vision catalog usable.
        try:
            image_response = requests.get(f'{OPENROUTER_BASE}/images/models', headers=headers, timeout=8)
            image_response.raise_for_status()
            known_ids = {row['id'] for row in модели}
            for item in image_response.json().get('data', []):
                ident = item.get('id')
                caps = capabilities('OpenRouter', ident, item.get('architecture') or {})
                if ident and ident not in known_ids and caps['image_generation']:
                    модели.append({'id': ident, 'note': item.get('name') or 'Генерация изображений', 'free': False, 'capabilities': caps})
                    known_ids.add(ident)
        except Exception:
            pass
        try:
            from .model_capabilities import remember_openrouter
        except ImportError:
            from model_capabilities import remember_openrouter
        remember_openrouter(модели)
        модели.sort(key=lambda m: (not m.get("free"), m["id"]))
        return модели
    except Exception as e:
        print(f"⚠️ Не удалось получить список моделей OpenRouter: {e}")
        return []

try:
    from . import key_ring as key_ring_module
except ImportError:
    import key_ring as key_ring_module


AI_CONFIG_PATH = Path(__file__).resolve().parent / "data" / "ai_config.json"


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


def _looks_like_bad_key(reason: str) -> bool:
    """Похоже ли, что провайдер отверг именно ключ, а не модель."""
    text = (reason or "").lower()
    return any(marker in text for marker in (
        "invalid api key", "invalid_api_key", "unauthorized", "401",
        "authentication", "no auth credentials",
    ))


def first_message(payload: dict) -> str:
    """
    Достать текст ответа из обычного для OpenAI устройства ответа.

    Каждый шаг здесь защищён, и это не перестраховка. Живая проверка показала:
    часть бесплатных моделей отвечает кодом 200, но кладёт в content пустоту —
    null вместо текста. Прямое обращение по цепочке падало с «NoneType has no
    attribute strip», и человек видел внутреннюю ошибку Scott вместо честного
    «модель не ответила».
    """
    choices = payload.get("choices") or []
    if not choices:
        return ""

    message = choices[0].get("message") or {}
    return (message.get("content") or "").strip()


def raise_with_body(response) -> None:
    """
    Проверить ответ и, если это отказ, бросить исключение с телом внутри.

    `raise_for_status` кладёт в текст исключения только код и адрес, а
    объяснение сервис пишет в теле. Так терялось самое нужное: на нулевом
    балансе в теле прямым текстом стояло «credit balance is too low», а
    человек видел «400 Client Error» и шёл перепроверять ключ.
    """
    if response.status_code < 400:
        return

    body = (response.text or "").strip()
    raise RuntimeError(f"{response.status_code}: {body[:500]}" if body
                       else f"{response.status_code}")


def explain_connect_error(provider: str, model: str, reason: str) -> str:
    """
    Перевести отказ провайдера на человеческий язык.

    Человеку в Настройках нужно знать, что делать дальше: перепроверить ключ,
    включить VPN или выбрать другую модель. Сырое «Connection error» из
    библиотеки на этот вопрос не отвечает.
    """
    text = (reason or "").lower()

    if _looks_like_bad_key(reason):
        return (f"{provider} не принял ключ. Проверьте, что скопировали его целиком "
                "и без пробелов, и что он не отозван в личном кабинете")

    if any(marker in text for marker in ("connection", "timed out", "timeout",
                                         "name or service", "getaddrinfo", "ssl")):
        return (f"Не удалось связаться с {provider}. Проверьте интернет; "
                "в некоторых странах доступ к этому сервису закрыт и нужен VPN")

    # Кончились деньги. Отличать этот случай от прочих важно: ключ здесь
    # верный, модель верная, интернет работает, и человек, читающий «не удалось
    # подключиться», пойдёт перепроверять ключ вместо того, чтобы заглянуть в
    # счёт. У Anthropic и OpenAI бесплатного тарифа нет вовсе, а у DeepSeek
    # деньги просто кончаются.
    if any(marker in text for marker in (
            "credit balance", "insufficient", "quota", "payment required",
            "402", "billing", "exceeded your current quota")):
        return (f"У {provider} закончились средства на счету. Ключ рабочий — "
                "пополните баланс в личном кабинете или выберите другого "
                "провайдера: у OpenRouter есть бесплатные модели")

    if any(marker in text for marker in ("model", "does not exist", "not found", "404")):
        return (f"Модель «{model}» недоступна этому ключу — выберите другую в списке")

    if "rate limit" in text or "429" in text:
        return f"{provider} временно ограничил запросы — попробуйте через минуту"

    if reason:
        return f"{provider} ответил: {reason[:200]}"

    return f"Не удалось подключиться к {provider} (модель «{model}») с этим ключом"


CONVERSATION_PATH = Path(__file__).resolve().parent / "data" / "conversations.jsonl"
LEGACY_CHAT_PATH = Path(__file__).resolve().parent.parent / "data" / "memory.jsonl"


class ConversationMemory:
    """Управление памятью разговоров"""
    
    def __init__(self, max_history: int = 20, context_file: Optional[Path] = None):
        self.max_history = max(2, max_history)
        self._lock = threading.RLock()
        self.conversations = []
        self.context_file = Path(context_file) if context_file is not None else CONVERSATION_PATH
        try:
            from .conversation_archive import ConversationArchive
        except ImportError:
            from conversation_archive import ConversationArchive
        self.archive = ConversationArchive(self.context_file.with_suffix('.sqlite3'))
        self._legacy_paths = [self.context_file]
        if context_file is None:
            self._legacy_paths.append(LEGACY_CHAT_PATH)
        self.history_warning = ''
        self._load_history()
        self.archive.start_semantic_index()
    
    def _load_history(self):
        """Загрузить историю разговоров"""
        try:
            self.archive.migrate(self._legacy_paths, refresh=[self.context_file])
            for user, assistant, timestamp in self.archive.recent(self.max_history // 2):
                self.conversations.extend([
                    {'role': 'user', 'content': user, 'timestamp': timestamp},
                    {'role': 'assistant', 'content': assistant, 'timestamp': timestamp}])
            return
        except Exception:
            self.history_warning = 'Архив разговоров недоступен; используется последняя история.'
            print(f'⚠️ {self.history_warning}')
        if self.context_file.exists():
            try:
                with open(self.context_file, 'r', encoding='utf-8') as f:
                    messages = deque(maxlen=self.max_history + 1)
                    for line in f:
                        try:
                            message = json.loads(line)
                        except (ValueError, TypeError):
                            continue
                        if (isinstance(message, dict) and message.get("role") in ("user", "assistant")
                                and isinstance(message.get("content"), str) and message["content"].strip()):
                            # Recover complete turns from older files, including
                            # files containing a question from a failed request.
                            if message["role"] == "user":
                                if messages and messages[-1]["role"] == "user":
                                    messages.pop()
                                messages.append(message)
                            elif messages and messages[-1]["role"] == "user":
                                messages.append(message)
                    self.conversations = list(messages)
                    self.drop_unanswered()
                    self._trim()
                print(f"📚 Загружено {len(self.conversations)} сообщений истории")
            except Exception as e:
                print(f"⚠️ Ошибка загрузки истории: {e}")
                self.conversations = []
    
    def drop_unanswered(self) -> None:
        """
        Убрать последний вопрос, на который не ответили.

        Вопрос кладётся в память до запроса к модели, ответ — после удачного.
        Когда запрос не удался, вопрос остаётся висеть, и со следующим их
        оказывается два подряд. Anthropic такую переписку отвергает целиком:
        два сообщения от человека без ответа между ними — нарушение формата.
        Одна неудача ломала бы все последующие запросы, уже исправные.
        """
        with self._lock:
            while self.conversations and self.conversations[-1].get("role") == "user":
                self.conversations.pop()

    def _trim(self) -> None:
        self.conversations = self.conversations[-self.max_history:]
        while self.conversations and self.conversations[0]["role"] != "user":
            self.conversations.pop(0)

    def add_message(self, role: str, content: str):
        """Добавить сообщение в память"""
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        with self._lock:
            if role == "user":
                self.drop_unanswered()
            elif role != "assistant" or not self.conversations or self.conversations[-1]["role"] != "user":
                return
            self.conversations.append(message)
            self._trim()
            # Persist complete turns only. Failed requests stay out of the
            # history loaded after restart.
            if role == "assistant":
                self._save_message(message)
    
    def _save_message(self, message: Dict):
        """Сохранить сообщение в файл"""
        try:
            user, assistant = self.conversations[-2:]
            self.archive.add(user['content'], assistant['content'], user.get('timestamp', ''))
            self.history_warning = ''
        except Exception:
            self.history_warning = 'Не удалось записать постоянную историю разговора.'
            print(f'⚠️ {self.history_warning}')
        try:
            atomic_write_text(self.context_file, "".join(
                json.dumps(item, ensure_ascii=False) + "\n" for item in self.conversations))
        except Exception as e:
            print(f"⚠️ Ошибка сохранения: {e}")
    
    def get_context(self, max_chars=None) -> List[Dict]:
        """Получить контекст для отправки в API"""
        with self._lock:
            messages = [{"role": msg["role"], "content": msg["content"]} for msg in self.conversations]
        try:
            from .memories import history_allowed
        except ImportError:
            from memories import history_allowed
        pending = messages[-1:] if messages and messages[-1]['role'] == 'user' else []
        completed = messages[:-1] if pending else messages
        messages = [message for i in range(0, len(completed) - 1, 2)
                    if history_allowed(completed[i]['content'], completed[i + 1]['content'])
                    for message in completed[i:i + 2]] + pending
        if max_chars is None:
            return messages
        try:
            from .memory_retrieval import excerpt
        except ImportError:
            from memory_retrieval import excerpt
        pending = messages[-1:] if messages and messages[-1]['role'] == 'user' else []
        completed = messages[:-1] if pending else messages
        query = pending[0]['content'] if pending else ''
        budget = max(0, max_chars - sum(len(m['content']) for m in pending))
        pairs = []
        for index in range(len(completed) - 2, -1, -2):
            user, assistant = completed[index:index + 2]
            pair = [{'role': 'user', 'content': excerpt(user['content'], query, 800)},
                    {'role': 'assistant', 'content': excerpt(assistant['content'], query, 1200)}]
            cost = sum(len(m['content']) for m in pair)
            if cost > budget:
                continue
            pairs.insert(0, pair)
            budget -= cost
        return [message for pair in pairs for message in pair] + pending

    def recall(self, query):
        with self._lock:
            completed = self.conversations[:-1] if self.conversations and self.conversations[-1]['role'] == 'user' else self.conversations
            excluded = [(completed[i]['content'], completed[i + 1]['content']) for i in range(0, len(completed) - 1, 2)]
        try:
            return self.archive.recall(query, excluded)
        except Exception:
            return []

    def record_external_turn(self, user, assistant):
        """Include local answers and voice commands without disturbing an active LLM request."""
        if not user.strip() or not assistant.strip():
            return
        with self._lock:
            if len(self.conversations) >= 2 and (self.conversations[-2]['content'], self.conversations[-1]['content']) == (user, assistant):
                return
            timestamp = datetime.now().isoformat()
            try:
                self.archive.add(user, assistant, timestamp)
                self.history_warning = ''
            except Exception:
                self.history_warning = 'Не удалось записать постоянную историю разговора.'
            if self.conversations and self.conversations[-1]['role'] == 'user':
                return
            self.conversations.extend([{'role': 'user', 'content': user, 'timestamp': timestamp},
                                       {'role': 'assistant', 'content': assistant, 'timestamp': timestamp}])
            self._trim()
            try:
                atomic_write_text(self.context_file, ''.join(json.dumps(item, ensure_ascii=False) + '\n' for item in self.conversations))
            except OSError:
                self.history_warning = 'Не удалось записать последнюю историю разговора.'

    def stats(self):
        try:
            turns = self.archive.count()
        except Exception:
            turns = 0
        return {'archived_turns': turns, 'recent_messages': len(self.conversations), 'warning': self.history_warning}
    
    def clear(self):
        """Очистить память"""
        with self._lock:
            try:
                self.archive.clear(lambda: atomic_write_text(self.context_file, ''))
            except Exception as error:
                raise OSError('Не удалось очистить историю разговоров') from error
            self.conversations = []
            self.history_warning = ''


# Отдельный запрос для вопросов, заданных голосом.
#
# Не приписка к обычному, а замена. В обычном есть правило «используй примеры и
# аналогии для объяснения», и оно тянет в прямо противоположную сторону:
# приписанная просьба быть кратким ей проигрывала — проверено живьём, ответ
# остался на триста с лишним знаков.
#
# Речь идёт вдвое медленнее чтения: ответ на четыреста знаков Scott читает
# двадцать пять секунд, и всё это время микрофон приглушён — перебить его
# нельзя даже словом. В чате тот же ответ читают глазами за пару секунд,
# поэтому краткость нужна только вслух.
BRIEF_SYSTEM_PROMPT = """Ты Scott AI — голосовой помощник. Твой ответ будет
произнесён вслух, поэтому он должен быть коротким.

ПРАВИЛА:
1. Отвечай на русском, одним-двумя короткими предложениями.
2. Никаких списков, заголовков, звёздочек и разметки — всё это будет прочитано
   вслух как есть.
3. Скажи только главное. Без примеров, аналогий и вступлений вроде «проще
   говоря».
4. Не знаешь — скажи коротко и честно.
"""

# Предел на длину короткого ответа. Одной просьбы бывает мало: модель
# увлекается и договаривает мысль до конца, сколько бы её ни просили.
BRIEF_MAX_TOKENS = 160


# Провайдеры, чьи модели умеют смотреть картинки.
#
# Список именно провайдеров, а не моделей: у Anthropic и OpenAI зрение есть у
# всех нынешних разговорных моделей, а у шлюза оно зависит от выбранной — но
# проверить это заранее нельзя, и отказывать наперёд неправильно.
#
# Groq и DeepSeek сюда не входят: их модели работают только с текстом.
VISION_PROVIDERS = ("Anthropic", "OpenAI", "OpenRouter")


def provider_sees_images(provider: str) -> bool:
    """Умеет ли провайдер принимать картинки вместе с вопросом."""
    return provider in VISION_PROVIDERS


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
            # Оба имени, и это не прихоть. Компания называется Anthropic, а
            # модель — Claude, и человек, заводящий ключ, пишет то, что видит
            # у себя в личном кабинете. Ровно на этом ключ однажды и не
            # подхватился: он лежал в .env под именем CLAUDE_API_KEY, а Scott
            # искал ANTHROPIC_API_KEY и молча не находил ничего.
            "Anthropic": os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY"),
            "OpenRouter": os.getenv("OPENROUTER_API_KEY"),
        }

        # Связка ключей шлюза.
        #
        # Бесплатные модели ограничены числом запросов, и один ключ упирается
        # в предел быстро. Запасные подхватываются сами: иначе человеку
        # пришлось бы править настройки и перезапускать backend посреди
        # работы, хотя он всего лишь задал вопрос.
        self.openrouter_ring = key_ring_module.KeyRing([
            os.getenv("OPENROUTER_API_KEY") or "",
            os.getenv("OPENROUTER_API_KEY_2") or "",
            os.getenv("OPENROUTER_API_KEY_3") or "",
        ])

        if len(self.openrouter_ring) > 1:
            print(f"🔑 Ключей OpenRouter: {len(self.openrouter_ring)} "
                  "(запасные подхватятся при исчерпании предела)")
        # Ключи, явно введённые пользователем через Настройки (в приоритете над .env)
        self.custom_keys: Dict[str, str] = {}

        # Сохранённая настройка, которую пока не удалось применить: к ней
        # возвращаемся при первом обращении, а не забываем до перезапуска.
        self.pending_config: Optional[Dict] = None

        connected = False
        saved = self._load_saved_config()
        if saved and saved.get("provider") and saved.get("model"):
            keys = saved.get("keys", {})
            if isinstance(keys, dict):
                self.custom_keys.update({name: key for name, key in keys.items()
                                         if isinstance(key, str) and key.strip()})
            if saved.get("api_key"):
                self.custom_keys[saved["provider"]] = saved["api_key"]
            resolved_key = self.custom_keys.get(saved["provider"]) or self.env_keys.get(saved["provider"])
            connected = self._connect_provider(saved["provider"], saved["model"], resolved_key)
            if connected:
                print(f"✅ Восстановлена сохранённая конфигурация ИИ: {saved['provider']} / {saved['model']}")
            else:
                # Не выбрасываем настройку из головы: backend стартует вместе с
                # загрузкой моделей, часто сразу после включения компьютера,
                # когда сеть ещё не поднялась. Одна неудачная попытка не повод
                # заставлять человека вводить ключ заново — попробуем ещё раз
                # при первом же вопросе.
                self.pending_config = saved
                print(f"⚠️ Пока не удалось подключиться к {saved['provider']} — "
                      "повторю при первом обращении")

        # Приоритет по умолчанию (если нет сохранённой конфигурации или она не сработала):
        # Groq → DeepSeek → OpenAI
        if not connected and GROQ_AVAILABLE and self.env_keys["Groq"]:
            connected = self._connect_provider("Groq", "openai/gpt-oss-120b", self.env_keys["Groq"])

        if not connected and self.env_keys["DeepSeek"] and REQUESTS_AVAILABLE:
            connected = self._connect_provider("DeepSeek", "deepseek-chat", self.env_keys["DeepSeek"])

        if not connected and self.env_keys["Anthropic"] and REQUESTS_AVAILABLE:
            connected = self._connect_provider(
                "Anthropic", "claude-sonnet-5", self.env_keys["Anthropic"])

        if not connected and self.env_keys["OpenRouter"] and REQUESTS_AVAILABLE:
            connected = self._connect_provider(
                "OpenRouter", "anthropic/claude-sonnet-5", self.env_keys["OpenRouter"])

        if not connected and self.env_keys["OpenAI"] and OPENAI_AVAILABLE:
            connected = self._connect_provider("OpenAI", "gpt-3.5-turbo", self.env_keys["OpenAI"])

        # Если ничего не работает
        if not self.enabled:
            print("⚠️ Ни Groq, DeepSeek ни OpenAI не доступны!")
            print("   Используем fallback ответы для базовых вопросов")

        # Последняя причина неудачного подключения — её показывают человеку в
        # Настройках вместо общей фразы «не удалось подключиться».
        self.last_connect_error = ""

        # Память разговоров
        # Keep more short turns; the API context is bounded by characters.
        # Older complete turns remain in the searchable SQLite archive.
        self.memory = ConversationMemory(max_history=20)
        
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

    def instructions(self, brief: bool = False, query: str = '') -> str:
        """
        Системное указание модели — вместе с тем, что человек о себе рассказал.

        Персонализация добавляется ПОСЛЕ основных правил и не может их
        отменить: характер меняет тон, а не обязанности. Иначе «отвечай
        коротко» стало бы способом обойти всё остальное.

        Пока человек ничего не настроил, добавка пуста, и поведение ровно
        прежнее.
        """
        основа = BRIEF_SYSTEM_PROMPT if brief else self.system_prompt

        try:
            try:
                from . import personality
            except ImportError:
                import personality

            добавка = personality.prompt_addition()
        except Exception:
            # Персонализация — улучшение, а не условие работы: не прочиталась —
            # отвечаем как раньше.
            добавка = ""

        # То, что человек просил запомнить. Отдельно от персонализации: она о
        # том, КАК говорить, а это — что Scott знает.
        try:
            try:
                from . import memories
            except ImportError:
                import memories

            помнит = memories.prompt_addition(query)
            if помнит:
                добавка = (добавка + "\n\n" + помнит) if добавка else помнит
        except Exception:
            pass

        # Над чем человек работает сейчас. Только текущий проект: перечислять
        # все — значит платить за это в каждом вопросе.
        try:
            try:
                from . import projects
            except ImportError:
                import projects

            работа = projects.prompt_addition()
            if работа:
                добавка = (добавка + "\n\n" + работа) if добавка else работа
        except Exception:
            pass

        if not добавка:
            return основа

        return основа + "\n\n" + добавка


    def _test_connection_groq(self):
        """
        Проверить, что работает и ключ, и выбранная модель.

        Одного списка моделей мало: он подтверждает только ключ, и человек с
        опечаткой в названии модели видел «готово», а потом каждый вопрос
        падал. Поэтому следом идёт самый маленький возможный запрос к самой
        модели — один токен.
        """
        try:
            print("🧪 Тестирование Groq API...")
            self.client.models.list()
            self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "ok"}],
                max_tokens=1,
            )
            print(f"✅ Groq API работает!")
        except Exception as e:
            key = getattr(self.client, "api_key", "")
            reason = str(e).replace(key, "[скрыто]") if isinstance(key, str) and key else str(e)
            print(f"⚠️ Ошибка тестирования Groq: {reason}")
            # Причину запоминаем: она нужна человеку в Настройках, а не только
            # в консоли, которой он не видит.
            self.last_connect_error = reason
            self.enabled = False
    
    def _test_connection_openai(self):
        """Проверить подключение к OpenAI API"""
        try:
            print("🧪 Тестирование OpenAI API...")
            # Простой тест - получить список моделей
            response = self.client.models.list()
            print(f"✅ OpenAI API работает!")
        except Exception as e:
            key = getattr(self.client, "api_key", "")
            reason = str(e).replace(key, "[скрыто]") if isinstance(key, str) and key else str(e)
            print(f"⚠️ Ошибка тестирования OpenAI: {reason}")
            self.last_connect_error = reason
            self.enabled = False

    def _connect_provider(self, provider: str, model: str, api_key: Optional[str]) -> bool:
        """Подключиться к конкретному провайдеру с конкретной моделью и ключом.
        Общая точка входа и для стандартной инициализации, и для ручного
        переключения через /ai/configure — раньше три провайдера подключались
        тремя копипастами кода в __init__."""
        if not api_key:
            return False

        self.last_connect_error = ""

        try:
            if provider == "Groq":
                if not GROQ_AVAILABLE:
                    self.last_connect_error = (
                        "библиотека groq не установлена — обновите Scott "
                        "или выполните: pip install groq"
                    )
                    return False
                self.client = Groq(api_key=api_key)
                self.enabled = True
                self.api_provider = "Groq"
                self.model = model
                print(f"✅ Groq API подключен (модель: {self.model})")
                self._test_connection_groq()
            elif provider == "DeepSeek":
                if not REQUESTS_AVAILABLE:
                    self.last_connect_error = "библиотека requests не установлена"
                    return False
                self.client = {"api_key": api_key, "base_url": "https://api.deepseek.com"}
                self.enabled = True
                self.api_provider = "DeepSeek"
                self.model = model
                print(f"✅ DeepSeek API подключен (модель: {self.model})")
            elif provider == "Anthropic":
                if not REQUESTS_AVAILABLE:
                    self.last_connect_error = "библиотека requests не установлена"
                    return False

                # Ключ проверяется сразу, списком моделей: запрос бесплатный, а
                # узнать об опечатке в Настройках гораздо лучше, чем при первом
                # заданном вопросе.
                #
                # Денег на счету он не проверяет — это выяснится только
                # настоящим запросом. Зато когда выяснится, объяснение будет
                # внятным, а не «400 Client Error».
                probe = requests.get(
                    f"{ANTHROPIC_BASE}/models",
                    headers={"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION},
                    timeout=15,
                )

                if probe.status_code != 200:
                    self.last_connect_error = explain_connect_error(
                        "Anthropic", model, probe.text).replace(api_key, "[скрыто]")
                    print(f"⚠️ {self.last_connect_error}")
                    return False

                self.client = {"api_key": api_key, "base_url": ANTHROPIC_BASE}
                self.enabled = True
                self.api_provider = "Anthropic"
                self.model = model
                print(f"✅ Anthropic API подключен (модель: {self.model})")
            elif provider == "OpenRouter":
                if not REQUESTS_AVAILABLE:
                    self.last_connect_error = "библиотека requests не установлена"
                    return False

                # Ключ, введённый руками в Настройках, встаёт первым в связке:
                # человек только что его выбрал, и пробовать сначала прежние
                # было бы странно.
                if api_key != self.openrouter_ring.current():
                    self.openrouter_ring = key_ring_module.KeyRing(
                        [api_key] + [key for key in self.openrouter_ring.all if key != api_key])

                self.client = {"api_key": api_key, "base_url": OPENROUTER_BASE}
                self.enabled = True
                self.api_provider = "OpenRouter"
                self.model = model
                print(f"✅ OpenRouter подключен (модель: {self.model})")
            elif provider == "OpenAI":
                if not OPENAI_AVAILABLE:
                    self.last_connect_error = "библиотека openai не установлена"
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
            reason = str(e).replace(api_key, "[скрыто]")
            print(f"⚠️ Ошибка подключения {provider}: {reason}")
            self.last_connect_error = reason
            self.client = None
            self.api_provider = None
            self.enabled = False
            return False

    def _load_saved_config(self) -> Optional[Dict]:
        """Загрузить сохранённый выбор провайдера/модели/ключа (см. /ai/configure)."""
        if AI_CONFIG_PATH.exists():
            try:
                with open(AI_CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, dict) else None
            except Exception as e:
                print(f"⚠️ Не удалось прочитать сохранённую конфигурацию ИИ: {e}")
        return None

    def _save_config(self, provider: str, model: str, api_key: Optional[str]) -> None:
        """Сохранить текущий выбор провайдера/модели/ключа на диск, чтобы он пережил перезапуск backend."""
        temporary = None
        try:
            AI_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = {"provider": provider, "model": model, "keys": dict(self.custom_keys)}
            if api_key:
                data["api_key"] = api_key
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=AI_CONFIG_PATH.parent,
                                             prefix=".ai-config-", suffix=".tmp", delete=False) as f:
                temporary = f.name
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, AI_CONFIG_PATH)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def configure(self, provider: str, model: str, api_key: Optional[str] = None) -> Dict:
        """
        Переключить активного провайдера и/или модель — с собственным API-ключом
        пользователя либо переиспользуя уже известный (ранее введённый или из .env).
        """
        resolved_key = api_key or self.custom_keys.get(provider) or self.env_keys.get(provider)
        if not resolved_key:
            return {"success": False, "error": f"Нет API-ключа для {provider} — укажите свой ключ"}

        # Probe a candidate while voice/chat continue using the current client.
        # A failed key or disk write must not temporarily disable working AI.
        candidate = copy.copy(self)
        candidate.custom_keys = dict(self.custom_keys)
        def accept(actual_model, note=None):
            # A running answer must keep the provider/client it started with.
            with self._state_lock():
                return commit(actual_model, note)

        def commit(actual_model, note=None):
            if api_key:
                candidate.custom_keys[provider] = api_key
            try:
                candidate._save_config(provider, actual_model, candidate.custom_keys.get(provider))
            except OSError:
                return {"success": False, "error": "Не удалось сохранить настройки модели на компьютере. Проверьте доступ к папке данных"}
            self.api_provider, self.model, self.client, self.enabled = candidate.api_provider, candidate.model, candidate.client, candidate.enabled
            self.custom_keys = candidate.custom_keys
            if hasattr(candidate, "openrouter_ring"):
                self.openrouter_ring = candidate.openrouter_ring
            self.pending_config = None
            result = {"success": True, "provider": provider, "model": actual_model}
            if note:
                result["note"] = note
            return result
        if not candidate._connect_provider(provider, model, resolved_key):
            reason = candidate.last_connect_error

            # Ключ может быть верным, а модель — недоступной этому аккаунту.
            # Спрашиваем у провайдера, что ему доступно, и пробуем первое из
            # списка: человеку незачем угадывать названия моделей.
            if provider == "Groq" and not _looks_like_bad_key(reason):
                for option in list_groq_models(resolved_key):
                    if option["id"] == model:
                        continue
                    if candidate._connect_provider(provider, option["id"], resolved_key):
                        return accept(option["id"], f"Модель «{model}» этому ключу недоступна — включил «{option['id']}»")

            # Откатываемся к прежнему рабочему состоянию, а не остаёмся сломанными
            return {"success": False, "error": explain_connect_error(provider, model, reason).replace(resolved_key, "[скрыто]")}

        return accept(model)

    def _ask_with_retry(self, call, provider: str):
        """
        Выполнить запрос к модели, пережив отказ по лимиту.

        Повторяется только то, что имеет смысл повторять: превышение лимита
        запросов и обрыв связи. Неверный ключ или несуществующая модель со
        второй попытки не исправятся — по ним отвечаем сразу.

        Паузу между попытками сервис часто называет сам, в заголовке
        `retry-after`; если нет — берём свою.
        """
        last_error = None

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return call()
            except Exception as e:
                last_error = e
                text = str(e).lower()

                retryable = any(marker in text for marker in (
                    "429", "rate limit", "too many requests",
                    "timeout", "timed out", "connection",
                    "502", "503", "504", "overloaded",
                ))

                if not retryable or attempt == MAX_ATTEMPTS:
                    raise

                pause = RETRY_PAUSE_SECONDS
                match = re.search(r"retry[- ]after[\"':\s]+([\d.]+)", text)
                if match:
                    try:
                        # Сервис знает лучше, сколько ждать, но ждать дольше
                        # таймаута самого запроса бессмысленно.
                        pause = min(float(match.group(1)), REQUEST_TIMEOUT_SECONDS)
                    except ValueError:
                        pass

                print(f"⏳ {provider} занят, повторю через {pause:.1f} с "
                      f"(попытка {attempt} из {MAX_ATTEMPTS})")
                time.sleep(pause)

        raise last_error  # pragma: no cover - до сюда не доходит

    def get_available_providers(self) -> List[Dict]:
        """Список провайдеров с их моделями и статусом — для выбора в Настройках."""
        providers = []

        groq_key = self.custom_keys.get("Groq") or self.env_keys.get("Groq")
        providers.append({
            "id": "Groq",
            "note": "Очень быстрые ответы, есть бесплатный тариф",
            "configured": bool(groq_key) and GROQ_AVAILABLE,
            # С ключом — живой список аккаунта, без ключа — запасной: иначе
            # выбрать модель невозможно, а без модели не применить ключ.
            "models": (list_groq_models(groq_key) or GROQ_FALLBACK_MODELS)
            if (groq_key and GROQ_AVAILABLE) else GROQ_FALLBACK_MODELS,
        })

        provider_notes = {
            "OpenAI": "Высокое качество ответов, платно",
            "DeepSeek": "Сильна в логике/математике, недорого",
            "Anthropic": "Claude: сильные ответы на русском, платно",
            "OpenRouter": "Один ключ — сотни моделей разных поставщиков",
        }

        # Провайдеры, у которых список моделей можно спросить живым запросом.
        # Он всегда точнее статического: модели появляются и снимаются чаще,
        # чем выходят версии Scott, и на этом уже обжигались — захардкоженная
        # модель Groq оказалась снята с поддержки, и Scott замолчал.
        live_lists = {
            "Anthropic": lambda key: list_anthropic_models(key),

            # У шлюза каталог открытый: его видно и без ключа, то есть до того,
            # как человек что-либо ввёл. Это ровно тот случай, ради которого
            # заводились статические каталоги, — здесь он решается честно.
            "OpenRouter": lambda key: list_openrouter_models(key or ""),
        }

        for provider_id, models in STATIC_PROVIDER_MODELS.items():
            key = self.custom_keys.get(provider_id) or self.env_keys.get(provider_id)

            fetch = live_lists.get(provider_id)
            live = fetch(key) if fetch and (key or provider_id == "OpenRouter") else []

            providers.append({
                "id": provider_id,
                "note": provider_notes.get(provider_id, ""),
                "configured": bool(key),
                "models": live or models,
            })

        try:
            from .model_capabilities import capabilities
        except ImportError:
            from model_capabilities import capabilities
        for provider in providers:
            if provider['id'] == 'OpenAI':
                provider['models'] = list(provider['models']) + [
                    {'id': 'gpt-image-2.5-sunburst', 'note': 'Генерация изображений'},
                    {'id': 'gpt-image-2.5-flare', 'note': 'Генерация изображений'},
                    {'id': 'gpt-image-1', 'note': 'Генерация изображений'},
                ]
            provider['models'] = [dict(row, capabilities=row.get('capabilities') or capabilities(provider['id'], row['id'])) for row in provider['models']]
        return providers

    def retry_pending_connection(self) -> bool:
        """
        Ещё раз применить настройку, которая не сработала при старте.

        Вызывается перед ответом: к этому времени сеть обычно уже поднялась.
        Возвращает True, если подключиться удалось.
        """
        if self.enabled or not self.pending_config:
            return False

        saved = self.pending_config
        key = self.custom_keys.get(saved["provider"]) or self.env_keys.get(saved["provider"])
        if not key:
            return False

        if self._connect_provider(saved["provider"], saved["model"], key):
            print(f"✅ Подключение к {saved['provider']} восстановлено со второй попытки")
            self.pending_config = None
            return True

        return False

    def _state_lock(self):
        return self.__dict__.setdefault("_answer_lock", threading.RLock())

    def answer(self, text: str, use_memory: bool = True, brief: bool = False) -> Tuple[str, bool]:
        # Chat and voice run on worker threads: preserve complete conversation
        # turns and prevent provider changes halfway through a request.
        with self._state_lock():
            return self._answer_locked(text, use_memory, brief)

    def _answer_locked(self, text: str, use_memory: bool = True, brief: bool = False) -> Tuple[str, bool]:
        """
        Получить ответ от ИИ (Groq или OpenAI)
        
        Args:
            text: Текст вопроса
            use_memory: Использовать ли контекст разговора
        
        Returns:
            (ответ, успех)
        """
        try:
            try:
                from . import memories
            except ImportError:
                import memories
            memories.observe(text)
        except Exception:
            print('⚠️ Не удалось обновить сведения пользователя в памяти')

        # Настройка могла не примениться при старте — сеть тогда ещё не
        # поднялась. Пробуем снова, прежде чем сказать «ИИ недоступен».
        self.retry_pending_connection()

        if not self.enabled or not self.client:
            return "❌ ИИ-ассистент недоступен. Используйте fallback ответы", False
        
        try:
            # Добавляем пользовательское сообщение в память
            self.memory.add_message("user", text)
            
            # Получаем контекст разговора
            instructions = self.instructions(brief, query=text)
            max_tokens = BRIEF_MAX_TOKENS if brief else self.max_tokens

            messages = [{"role": "system", "content": instructions}]
            if use_memory:
                messages.extend(self.memory.recall(text))
                messages.extend(self.memory.get_context(max_chars=6000))
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
                        "max_tokens": max_tokens,
                    },
                    timeout=30,
                )
                raise_with_body(response)
                answer = first_message(response.json())
                print(f"✅ DeepSeek ответ получен ({len(answer)} символов)")
            
            # Claude: у него другой разговорный формат.
            elif self.api_provider == "Anthropic":
                print(f"🟣 Anthropic API запрос ({self.model})...")

                # Системная подсказка идёт отдельным полем, а не первым
                # сообщением: Anthropic роли "system" в списке сообщений не
                # принимает и отвечает отказом на весь запрос.
                беседа = [m for m in messages if m["role"] != "system"]

                response = requests.post(
                    f"{ANTHROPIC_BASE}/messages",
                    headers={
                        "x-api-key": self.client["api_key"],
                        "anthropic-version": ANTHROPIC_VERSION,
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "system": instructions,
                        "messages": беседа,
                        "max_tokens": max_tokens,
                        "temperature": self.temperature,
                    },
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                raise_with_body(response)

                куски = response.json().get("content", [])
                answer = "".join(
                    кусок.get("text", "") for кусок in куски if кусок.get("type") == "text"
                ).strip()
                print(f"✅ Anthropic ответ получен ({len(answer)} символов)")

            # Шлюз к сотням моделей: формат тот же, что у OpenAI.
            elif self.api_provider == "OpenRouter":
                print(f"🌐 OpenRouter запрос ({self.model})...")
                answer = self._ask_openrouter({
                    "model": self.model,
                    "messages": messages,
                    "temperature": self.temperature,
                    "max_tokens": max_tokens,
                })
                print(f"✅ OpenRouter ответ получен ({len(answer)} символов)")

            # Используем Groq если доступен
            elif self.api_provider == "Groq":
                print(f"⚡ Groq API запрос ({self.model})...")
                response = self._ask_with_retry(
                    lambda: self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=self.temperature,
                        max_tokens=max_tokens,
                        timeout=REQUEST_TIMEOUT_SECONDS,
                    ),
                    provider="Groq",
                )
                answer = (response.choices[0].message.content or "").strip()
                print(f"✅ Groq ответ получен ({len(answer)} символов)")
            
            # Fallback на OpenAI
            elif self.api_provider == "OpenAI":
                print(f"🤖 OpenAI API запрос ({self.model})...")
                response = self._ask_with_retry(
                    lambda: self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=self.temperature,
                        max_tokens=max_tokens,
                        top_p=0.95,
                        presence_penalty=0.0,
                        frequency_penalty=0.0,
                        timeout=REQUEST_TIMEOUT_SECONDS,
                    ),
                    provider="OpenAI",
                )
                answer = (response.choices[0].message.content or "").strip()
                print(f"✅ OpenAI ответ получен ({len(answer)} символов)")
            
            else:
                self.memory.drop_unanswered()
                return "❌ Неизвестный провайдер API", False
            
            if not answer:
                raise RuntimeError("Модель вернула пустой ответ")
            # Сохраняем ответ в память
            self.memory.add_message("assistant", answer)
            return answer, True
        
        except Exception as e:
            # Неотвеченный вопрос убирается из памяти разговора.
            #
            # Вопрос кладётся туда до запроса, ответ — после удачного. Если
            # запрос не удался, в истории остаётся «висячий» вопрос, и со
            # следующим их становится два подряд. Для Anthropic это прямое
            # нарушение формата: два сообщения от человека без ответа между
            # ними он отвергает целиком. То есть одна неудача — скажем,
            # кончились деньги — ломала бы и все последующие запросы, уже
            # после пополнения счёта.
            self.memory.drop_unanswered()

            # Разбор причины тот же, что в Настройках. Подключиться можно и с
            # нулевым счётом — ключ верен, модель верна, а денег нет, — и
            # сырое «400 Client Error» отправляет человека перепроверять ключ,
            # который ни при чём.
            понятно = explain_connect_error(self.api_provider or "", self.model, str(e))
            print(f"⚠️ {понятно}")
            return f"❌ {понятно}", False
    
    def _ask_openrouter(self, payload: dict) -> str:
        """
        Запрос к шлюзу с перебором ключей.

        Ключ, упёршийся в предел запросов, откладывается, и запрос повторяется
        следующим. Это и есть смысл нескольких ключей: без перебора второй и
        третий лежали бы мёртвым грузом.

        Перебор не бесконечен — каждый ключ пробуется один раз. Иначе при
        общей беде вроде недоступной модели Scott ходил бы по кругу, пока не
        кончится терпение у человека.
        """
        ring = self.openrouter_ring
        последняя = None

        for _ in range(max(1, len(ring))):
            key = ring.current() or (self.client or {}).get("api_key")
            if not key:
                raise RuntimeError("нет ни одного ключа OpenRouter")

            response = requests.post(
                f"{OPENROUTER_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )

            if response.status_code < 400:
                answer = first_message(response.json())

                if not answer:
                    # Модель промолчала. Менять ключ бессмысленно — дело не в
                    # нём, — а притворяться, что ответ получен, тем более.
                    raise RuntimeError(
                        f"модель «{payload.get('model')}» вернула пустой ответ")

                return answer

            последняя = f"{response.status_code}: {(response.text or '')[:500]}"
            причина = key_ring_module.why_refused(последняя)

            if причина is None:
                # Менять ключ бессмысленно: беда не в нём.
                break

            есть_запасной = ring.set_aside(key, причина)
            подпись = "предел запросов" if причина == "rate" else "ключ не принят"
            print(f"🔁 OpenRouter: {подпись}, "
                  f"{'беру следующий ключ' if есть_запасной else 'запасных больше нет'}")

            if not есть_запасной:
                break

        raise RuntimeError(последняя or "OpenRouter не ответил")

    def sees_images(self) -> bool:
        """Умеет ли смотреть картинки нынешняя связка провайдера и модели."""
        try:
            from .model_capabilities import capabilities
        except ImportError:
            from model_capabilities import capabilities
        return bool(self.enabled) and capabilities(self.api_provider or '', self.model, refresh=True)['images']

    def answer_about_image(self, question: str, image_base64: str,
                           media_type: str = "image/png") -> Tuple[str, bool]:
        """
        Ответить на вопрос о картинке.

        Картинка передаётся отдельной частью сообщения, и форма записи у
        провайдеров разная: Anthropic ждёт данные в поле source, остальные —
        ссылку вида data:... в поле image_url.

        Память здесь не используется намеренно: разговор о картинке начинается
        с чистого листа, иначе модель принимается отвечать на предыдущий
        вопрос, увидев знакомый контекст.
        """
        if not self.enabled:
            return "ИИ не настроен: добавьте ключ в настройках", False

        if not self.sees_images():
            return (f"Выбранная модель ({self.api_provider}) не умеет смотреть "
                    "картинки — она работает только с текстом. Переключитесь в "
                    "настройках на Anthropic, OpenAI или OpenRouter с моделью, "
                    "которая видит изображения."), False

        ask = question.strip() or "Что на этом изображении? Опиши подробно."

        try:
            if self.api_provider == "Anthropic":
                response = requests.post(
                    f"{ANTHROPIC_BASE}/messages",
                    headers={
                        "x-api-key": self.client["api_key"],
                        "anthropic-version": ANTHROPIC_VERSION,
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "system": self.instructions(),
                        "max_tokens": self.max_tokens,
                        "messages": [{
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": media_type,
                                        "data": image_base64,
                                    },
                                },
                                {"type": "text", "text": ask},
                            ],
                        }],
                    },
                    timeout=REQUEST_TIMEOUT_SECONDS * 2,
                )
                raise_with_body(response)

                pieces = response.json().get("content", [])
                answer = "".join(
                    p.get("text", "") for p in pieces if p.get("type") == "text"
                ).strip()

                return answer, bool(answer)

            # OpenAI и шлюз говорят на одном языке.
            content = [
                {"type": "text", "text": ask},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{image_base64}"},
                },
            ]

            messages = [
                {"role": "system", "content": self.instructions()},
                {"role": "user", "content": content},
            ]

            if self.api_provider == "OpenRouter":
                answer = self._ask_openrouter({
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": self.max_tokens,
                })
                return answer, bool(answer)

            # Дальше — OpenAI через собственную библиотеку.

            # OpenAI через собственную библиотеку.
            result = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                timeout=REQUEST_TIMEOUT_SECONDS * 2,
            )
            answer = (result.choices[0].message.content or "").strip()
            return answer, bool(answer)

        except Exception as e:
            понятно = explain_connect_error(self.api_provider or "", self.model, str(e))
            print(f"⚠️ Не удалось разобрать картинку: {понятно}")
            return f"❌ {понятно}", False

    def answer_question(self, question: str, brief: bool = False) -> str:
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
        
        answer, success = self.answer(question, use_memory=True, brief=brief)
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
        with self._state_lock():
            self.model = model
        print(f"🔄 Модель изменена на: {model}")
    
    def set_temperature(self, temp: float):
        """Изменить креативность (0.0-1.0)"""
        with self._state_lock():
            self.temperature = max(0.0, min(1.0, temp))
        print(f"🔄 Креативность: {self.temperature}")
    
    def clear_memory(self):
        """Очистить память разговоров"""
        with self._state_lock():
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
