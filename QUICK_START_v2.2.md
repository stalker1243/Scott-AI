# 🚀 QUICK START: Scott AI v2.1

## 1️⃣ ЗАПУСК СИСТЕМЫ

### Запуск проекта (Windows)
```bash
# Откройте терминал в папке проекта
cd "c:\Users\SKYNET\OneDrive\Рабочий стол\Lutushev.pro\neyro"

# Запустите backend
.\.venv\Scripts\python.exe backend\main.py
# Должен показать: "🚀 FastAPI server running on http://0.0.0.0:8000"

# В другом терминале запустите Rust-лаунчер
cd rust_launcher
cargo run
```

## 2️⃣ ТЕСТИРОВАНИЕ

### В браузере или curl
```bash
# Простой вопрос
curl -X POST http://localhost:8000/ask ^
  -H "Content-Type: application/json" ^
  -d "{\"question\": \"Привет!\"}"

# Должен вернуть:
# {"success": true, "data": {"answer": "Привет! 👋", "type": "greeting", "quiet_mode": false}}

# Что ты умеешь?
curl -X POST http://localhost:8000/ask ^
  -H "Content-Type: application/json" ^
  -d "{\"question\": \"Что ты умеешь?\"}"
```

### Через Python
```python
import requests

# Спросить
response = requests.post('http://localhost:8000/ask',
    json={'question': 'Кто ты?'})

print(response.json()['data']['answer'])
# → "Я Scott AI - твой личный ИИ-ассистент..."
```

## 3️⃣ ОЗВУЧИВАНИЕ (NEW!)

```bash
# Озвучить текст
curl -X POST http://localhost:8000/text_to_speech ^
  -H "Content-Type: application/json" ^
  -d "{\"text\": \"Привет мир\"}" \
  --output audio.wav

# Воспроизвести
start audio.wav
```

## 4️⃣ КОНФИГУРАЦИЯ

### Файл `config.json`
```json
{
  "voice_enabled": true,           // Озвучивание ответов
  "tts_engine": "pyttsx3",         // TTS движок
  "language": "ru-RU",              // Язык
  "api_timeout": 30,                // Timeout для API
  "fallback_mode": true             // Fallback без ключей
}
```

### Переменные окружения (опционально)
```bash
# .env файл
GROQ_API_KEY=xxx          # Для Groq AI
OPENAI_API_KEY=xxx        # Для OpenAI
SEARCH_API_KEY=xxx        # Для поиска
```

## 5️⃣ ЧТО РАБОТАЕТ ✅

### Основное
- ✅ Приветствия и социальные вопросы
- ✅ Информация о системе (время, CPU, RAM, диск)
- ✅ Информация о программировании
- ✅ Научные факты
- ✅ Исторические события
- ✅ Озвучивание ответов
- ✅ Команды ОС (открыть программу, файл и т.д.)

### Примеры вопросов
```
"Привет"               → Приветствие
"Как дела?"            → Социальный ответ
"Которы час?"          → Текущее время
"Система"             → Статус компьютера
"Кто ты?"             → Информация о Scott
"Что ты умеешь?"      → Список возможностей
"Python хороший?"     → Обучающий ответ
"Открой блокнот"      → Откроет Notepad
```

## 6️⃣ СЛЕДУЮЩИЕ ШАГИ

### Текущий рабочий путь
- Основной UI теперь реализован в `rust_launcher/src/main.rs`.
- Старый frontend на `app.js`/`index.html` больше не является основным стартовым приложением.
- Для расширений интерфейса используйте `rust_launcher` и `egui`.

### Для разработчиков Rust-UI
1. Изучите `rust_launcher/src/main.rs`.
2. Добавьте кнопки и панели в `render_*` методах.
3. Для сохранения настроек используйте `launcher-config.json`.

## 7️⃣ ОТЛАДКА

### Проверить статус
```bash
curl http://localhost:8000/health
# → {"status": "healthy", "timestamp": "..."}

curl http://localhost:8000/ai/status
# → {"status": "ready", "components": {...}}
```

### Логи
```bash
# Backend логи выводятся в консоль
# Ищите 👍 для успеха, ❌ для ошибок, 📝 для информации

# Память сохраняется в:
# - backend/jarvis_memory.json (долгосрочная)
# - data/memory.jsonl (разговоры)
```

### Если не работает
1. Проверить Python версию: `python --version` (нужна 3.10+)
2. Проверить зависимости: `.\.venv\Scripts\pip list | grep -E "fastapi|pyttsx3"`
3. Перезапустить backend
4. Очистить кэш в `data/`

## 📚 ДОКУМЕНТАЦИЯ

- `FINAL_REPORT_v2.1.md` - Полный отчет о возможностях
- `SCOTT_AI_STATUS_v2.1.md` - Статус и roadmap
- `examples_api.py` - Примеры кода
- `README.md` - Основная документация

## 💬 ЧАСТО ЗАДАВАЕМЫЕ ВОПРОСЫ

**Q: Почему нет ответа на мой вопрос?**  
A: Добавьте его в `backend/extended_responses.py` или `backend/question_answerer.py`

**Q: Как включить ChatGPT?**  
A: Добавьте `OPENAI_API_KEY` в `.env` и установите `enabled=True` в `intelligent_answerer.py`

**Q: Почему медленно обрабатывает?**  
A: Проверьте использование CPU/RAM через `Который час?` → "система"

**Q: Как добавить свои команды?**  
A: Отредактируйте `command_parser.py` и `command_executor.py`

---

**Версия**: 2.1  
**Готовность**: 🟢 Готов к использованию  
**Поддержка**: Python 3.10+, Windows 10/11
