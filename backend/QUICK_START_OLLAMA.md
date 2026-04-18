# Быстрый старт с Ollama

Ollama успешно настроен и работает! 🎉

## Что у тебя работает

- ✅ Ollama сервер запущен
- ✅ Модель `qwen2.5:7b` установлена
- ✅ LLM движок подключен
- ✅ Чат-бот может использовать Ollama

## Использование Ollama в коде

### Простой пример:

```python
from llm_core import LlmEngine, LlmConfig

# Настройка Ollama
config = LlmConfig(
    provider="ollama",
    model="qwen2.5:7b"
)

llm = LlmEngine(config=config)
answer = llm.answer("Привет, как дела?")
print(answer)
```

### Использование в чат-боте:

```python
from llm_core import LlmEngine, LlmConfig
from chatbot import ChatBot, ChatBotConfig

# Настройка LLM
llm_config = LlmConfig(provider="ollama", model="qwen2.5:7b")
llm = LlmEngine(config=llm_config)

# Создание чат-бота
chatbot_config = ChatBotConfig(llm_engine=llm)
chatbot = ChatBot(config=chatbot_config)

# Использование
result = chatbot.process_text_question("Привет! Расскажи о себе")
print(result["answer_text"])
```

### Тест чат-бота с Ollama:

```bash
cd backend
python test_chatbot_ollama.py
```

## Что дальше?

Теперь можно:

1. **Подключить реальную TTS модель** - для озвучивания ответов
2. **Улучшить работу с видео** - обработка мультфильмов
3. **Создать мобильное приложение** - React Native клиент
4. **Улучшить интеграцию** - добавить больше функций

## Полезные команды Ollama

```bash
# Список моделей
ollama list

# Запустить другую модель
ollama run llama3.2

# Показать информацию о модели
ollama show qwen2.5:7b
```

## Рекомендации

- **Текущая модель `qwen2.5:7b`** отлично понимает русский язык
- Модель работает **локально**, данные не уходят в облако
- Ответы могут занимать **несколько секунд** (это нормально для локальных моделей)

---

**Готово!** Ты можешь использовать Ollama в своём проекте! 🚀

