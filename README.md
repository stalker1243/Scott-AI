# 🤖 SCOTT AI v3.0 - Голосовой ассистент как Джарвис

**Полнофункциональный голосовой AI ассистент** в стиле JARVIS из фильма "Железный человек"

## 🚀 БЫСТРЫЙ СТАРТ (30 СЕКУНД)

```
1. Установить Python 3.10+ → https://www.python.org/downloads/
2. Установить Rust + Cargo → https://www.rust-lang.org/tools/install
3. Запустить поддерживаемый лаунчер:
   launch.bat
4. ✅ ГОТОВО! Наслаждайся новым desktop-приложением! 🎤
```

> Поддерживается только один рабочий launcher: Rust launcher в папке rust_launcher. Все старые варианты запуска убраны из основного пути.

**Первый раз:** 20-30 минут (установка зависимостей)  
**Потом:** 3 секунды каждый раз! ⚡

---

## ✨ ЧТО НОВОГО В v3.0

### 🔧 Установка и запуск
✅ **Автоматический инсталлятор** - scott-ai-3.0.0-setup.exe  
✅ **Портативная версия** - scott-ai-3.0.0-portable.exe  
✅ **One-click запуск** - `cargo run --manifest-path rust_launcher/Cargo.toml`  
✅ **Native Rust launcher** - `rust_launcher/`  

### 🔄 Система обновлений
✅ **Версионирование** - Semantic Versioning (3.0.0)  
✅ **Ручная проверка** - Кнопка в UI  
✅ **Автоматическая проверка** - Фоновый мониторинг  
✅ **Интервал проверки** - 1ч, 6ч, 12ч, 24ч, 7дней  
✅ **Тихий режим** - Без уведомлений ночью (22:00-08:00)  
✅ **История версий** - Полный changelog  

### ⚙️ Настройки
✅ **Страница настроек** - Удобный интерфейс  
✅ **REST API** - Для интеграции  
✅ **Логирование** - update_monitor.log  
✅ **Конфиг файл** - config_settings.json  

---

## 🎯 Характеристики

✅ **Голос Джарвиса** - Синтез речи с британским акцентом  
✅ **Распознавание речи** - OpenAI Whisper (локально)  
✅ **Искусственный интеллект** - Ollama (локально) + fallback ответы  
✅ **Система команд** - Открытие программ, создание файлов, управление браузером  
✅ **Мониторинг системы** - CPU, RAM, GPU, диск в реальном времени  
✅ **3D Голограмма** - Визуализация метрик на PySide6  
✅ **WebSocket связь** - Двусторонняя коммуникация  
✅ **База памяти** - Сохранение разговоров и фактов  

---

## 📁 Структура проекта

```
scott-ai/
├── 🎯 ЗАПУСК (ГЛАВНОЕ)
│   ├── package.json                     ← Запуск Rust-лаунчера
│   ├── rust_launcher/                   ← Native Rust launcher UI
│   └── backend/                        ← FastAPI backend
│
├── 📦 УСТАНОВКА И ВЕРСИОНИРОВАНИЕ
│   ├── VERSION.json                     ← Манифест версий
│   ├── config_settings.json             ← Настройки приложения
│   ├── scott_installer.nsi              ← NSIS инсталлер
│   └── build_standalone.py              ← Сборка в exe
│
├── 🔄 СИСТЕМА ОБНОВЛЕНИЙ
│   ├── update_monitor.py                ← Фоновый мониторинг
│   ├── backend/version_endpoints.py     ← REST API для версий
│   ├── rust_launcher/                   ← Native Rust launcher UI
│   └── update_monitor.log               ← Логи (создается)
│
├── backend/
│   ├── main.py                      # FastAPI сервер
│   ├── jarvis_voice.py              # Синтез речи (Джарвис)
│   ├── speech_recognition.py        # Распознавание (Whisper)
│   ├── command_executor.py          # Выполнение команд
│   ├── knowledge_base.py            # Память и AI
│   ├── system_monitor.py            # Мониторинг системы
│   ├── voice_endpoints.py           # REST API для голоса
│   ├── version_endpoints.py         # REST API для версий ← НОВОЕ!
│   ├── requirements.txt
│   └── jarvis_memory.json           # База памяти
│
├── docker-compose.yml               # Ollama конфигурация
├── README.md                        # Этот файл
└── .env                             # Переменные окружения (опционально)
```

---

## 🚀 БЫСТРЫЙ СТАРТ (3 ВАРИАНТА)

### ⚡ Способ 1: ОДИН КЛИК (РЕКОМЕНДУЕТСЯ)

```
cargo run --manifest-path rust_launcher/Cargo.toml
```

Это всё что нужно! Команда автоматически:
- ✅ Запускает Rust-лаунчер
- ✅ Контролирует состояние backend
- ✅ Позволяет отправлять команды и чат
- ✅ Показывает системный статус и активность

### �️ Способ 2: Ручной запуск (для разработчиков)

```bash
# Подготовка (первый раз)
python -m venv venv
venv\Scripts\activate

# Backend
cd backend
pip install -r requirements.txt

# Запуск backend
python main.py
```

```bash
# Подготовка (первый раз)
python -m venv venv
venv\Scripts\activate

# Backend
cd backend
pip install -r requirements.txt

# Запуск backend
python main.py

# В другом терминале — Rust-лаунчер
cd ../rust_launcher
cargo run
```

### 2️⃣ Запустить Backend

```bash
cd backend
python main.py
```

**Ожидаемый вывод:**
```
==================================================
🚀 JARVIS AI ASSISTANT - BACKEND STARTED
==================================================
✅ FastAPI сервер запущен
✅ WebSocket доступен: ws://localhost:8000/ws/chat
✅ REST API доступен: http://localhost:8000
📚 API документация: http://localhost:8000/docs
==================================================
```

### 3️⃣ Запустить Rust launcher (в отдельном терминале)

```bash
cd rust_launcher
cargo run
```

**Появится приложение с:**
- Сайдбаром: Обзор, Ассистент, Инструменты, Настройки
- Статусом backend и быстрыми действиями
- Чатом и системой управления

---

## 🧠 Использование AI (Ollama)

Для полноценного AI:

### Установить Ollama

1. Скачать: https://ollama.ai/
2. Установить и запустить
3. В терминале Ollama:

```bash
ollama pull neural-chat
```

### Запустить Ollama сервер

```bash
ollama serve
```

Теперь JARVIS будет использовать локальный LLM!

---

## 💬 Примеры команд

Вводите в чат:

```
"Hello JARVIS"                          # Приветствие
"Open notepad"                          # Открыть программу
"Search for Python tutorial"            # Поиск в браузере
"Open www.google.com"                   # Открыть сайт
"Create file my_file.txt"               # Создать файл
"Create folder my_folder"               # Создать папку
"System status"                         # Информация о системе
"Who are you?"                          # О себе
"Remember my name is John"              # Сохранить в память
```

---

## 🎙️ Голосовые команды (будущее)

Планируется добавить:
- Запись голоса через микрофон
- Распознавание речи в реальном времени
- Озвучивание ответов

---

## 🔧 API Endpoints

### REST

```
GET  /health                 # Проверка сервера
GET  /metrics                # Метрики системы
GET  /processes              # Список процессов
POST /command                # Выполнить команду
```

### WebSocket

```
ws://localhost:8000/ws/chat
```

**Формат сообщения:**
```json
{
  "type": "text",
  "text": "Your command here",
  "speak": true
}
```

---

## 📊 Архитектура

```
┌─────────────────────────────────────┐
│    Rust Launcher UI                 │
│  ├─ Ассистент                       │
│  ├─ Система                         │
  ├─ Инструменты                     │
│  └─ Настройки                       │
└──────────────┬──────────────────────┘
               │ HTTP / REST
               ↓
┌─────────────────────────────────────┐
│    Backend (FastAPI)                │
│  ├─ Command Executor                │
│  ├─ Knowledge Base + Memory          │
│  ├─ AI Brain (Ollama)               │
│  ├─ Speech Recognition              │
│  ├─ TTS (Джарвис голос)             │
│  └─ System Monitor                  │
└─────────────────────────────────────┘
```

---

## 🎨 Дизайн

- **Тёмная тема** - Чёрный фон с зелёным текстом (Matrix стиль)
- **3D Голограмма**:
  - Голова = ЦП (красный/жёлтый/зелёный)
  - Торс = ОЗУ (красный/жёлтый/зелёный)
  - Ноги = Процессы
  - Платформа = Основание

---

## ⚙️ Требования

- **Python 3.10+**
- **Rust + Cargo** (для запуска лаунчера)
- **Windows 10+** (для TTS)
- **4GB ОЗУ** минимум
- **Интернет** (для edge-tts)

### Дополнительно:
- **GPU** (Nvidia CUDA) - для ускорения Ollama
- **Микрофон** - для голосовых команд (будущее)

---

## 🐛 Решение проблем

### "Не работает TTS"
```bash
# Переустановить pydub
pip install pydub --upgrade

# Установить ffmpeg (Windows)
# Скачать: https://ffmpeg.org/download.html
```

### "Ollama не подключается"
```bash
# Убедитесь что Ollama запущена:
ollama serve

# Проверить на http://localhost:11434
```

### "WebSocket ошибка"
```bash
# Перезапустить Rust-лаунчер
cd rust_launcher
cargo run

# Убедитесь что backend запущен
python backend/main.py
```

---

## 📝 Логи

- **Backend логи**: Будут в консоли
- **Launcher логи**: Будут в консоли
- **Память**: `backend/jarvis_memory.json`

---

## 🚀 Развёртывание

### Локально (текущее)
```bash
# Запустить backend
python backend/main.py

# В отдельном терминале запустить Rust-лаунчер
cargo run --manifest-path rust_launcher/Cargo.toml
```

### Docker (будущее)
```bash
docker-compose up
```

---

## 🧠 ChatGPT интеграция (OpenAI API)

**NEW!** Теперь Scott AI имеет полную поддержку ChatGPT для интеллектуальных ответов!

### ✨ Возможности
- ✅ Ответы на любые вопросы (как ChatGPT)
- ✅ Память разговоров (контекст-зависимые ответы)  
- ✅ Выбор моделей (GPT-3.5 Turbo / GPT-4 / GPT-4 Turbo)
- ✅ Контроль креативности (Temperature)
- ✅ Локальное хранение разговоров

### 🚀 Активация (5 минут)

**Для быстрого старта:**
1. Получите API ключ: https://platform.openai.com/api-keys
2. Добавьте в файл `.env`: `OPENAI_API_KEY=sk-ваш-ключ`
3. Перезагрузите приложение
4. Перейдите в ⚙️ Настройки → 🧠 ИИ и включите

**Подробное руководство:** [OPENAI_SETUP.md](OPENAI_SETUP.md)  
**Быстрый чек-лист:** [AI_ACTIVATION_CHECKLIST.md](AI_ACTIVATION_CHECKLIST.md)

### 💰 Стоимость
- **Дешево**: ~$0.0005-0.01 за вопрос
- **Первые $5 бесплатно** при регистрации
- **Контроль расходов**: Установите лимит в настройках OpenAI

---

## 📚 Документация и ресурсы

### 📖 Документация (НОВОЕ v3.0)
- **START_HERE.txt** - Для новичков (начни отсюда!)
- **QUICK_INSTALL_GUIDE.md** - Быстрая установка (10 мин)
- **INSTALLATION_AND_UPDATES.md** - Полная инструкция (разработчикам)
- **SYSTEM_COMPLETE_GUIDE.md** - Полный гайд всей системы
- **README_SYSTEM_COMPLETE.md** - Итоговое резюме

### 🌐 API и интеграция
- **FastAPI docs**: http://localhost:8000/docs
- **REST API**: /api/version/* endpoints (новые!)
- **WebSocket**: ws://localhost:8000/ws/chat

### 📦 Внешние ресурсы
- **Whisper**: https://github.com/openai/whisper
- **Ollama**: https://ollama.ai/
- **Rust**: https://www.rust-lang.org/
- **Python**: https://www.python.org/downloads/

---

## 🔐 Системные требования

| Требование | Минимум | Рекомендуется |
|----------|---------|-------------|
| **ОС** | Windows 10 | Windows 10/11 |
| **Python** | 3.10 | 3.12+ |
| **Rust + Cargo** | 1.0 | latest |
| **ОЗУ** | 2 ГБ | 4+ ГБ |
| **Дисковое пространство** | 500 МБ | 1 ГБ |
| **Интернет** | Требуется | Требуется (для API) |

---

## 👨‍💻 Разработка

Модули для расширения:

1. **speech_recognition.py** - Добавить другие языки
2. **command_executor.py** - Добавить новые команды
3. **knowledge_base.py** - Улучшить AI логику
4. **rust_launcher/src/main.rs** - Улучшить native Rust UI

---

## 📄 Лицензия

MIT License - Используйте свободно!

---

## 🤝 Автор

Создано для **максимальной впечатляющести** 🎬✨

Версия: **1.0 Pro Edition**  
Дата: **17 Мая 2026**

---

## 📞 Контакты

Приложение полностью функционально и готово к презентации!

**Enjoy JARVIS! 🤖**
