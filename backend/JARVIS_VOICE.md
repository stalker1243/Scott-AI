# Голос Джарвиса (J.A.R.V.I.S.)

🎉 **Отличная идея!** Теперь можно использовать голос в стиле Джарвиса из "Железного человека"!

## Доступные варианты

### 1. Джарвис (английский) - как в фильме 🇬🇧
- Голос: `en-GB-RyanNeural` (британский мужской)
- Скорость: немного медленнее (-10%)
- Тон: глубже (-15Hz)
- **Пресет**: `"jarvis"`

### 2. Джарвис (русский) 🇷🇺
- Голос: `ru-RU-DmitryNeural` (русский мужской)
- Скорость: медленнее (-10%)
- Тон: глубже (-20Hz)
- **Пресет**: `"jarvis_ru"`

## Использование

### Простой способ (через пресет):

```python
from tts_core import TtsConfig, TtsEngine

# Русский вариант Джарвиса
config = TtsConfig(voice_preset="jarvis_ru")
tts = TtsEngine(config=config)

# Английский вариант (как в фильме)
config_en = TtsConfig(voice_preset="jarvis")
tts_en = TtsEngine(config=config_en)
```

### В чат-боте:

```python
from tts_core import TtsConfig
from chatbot import ChatBot, ChatBotConfig

tts_config = TtsConfig(voice_preset="jarvis_ru")  # Голос Джарвиса
tts = TtsEngine(config=tts_config)

chatbot_config = ChatBotConfig(tts_engine=tts)
chatbot = ChatBot(config=chatbot_config)
```

### Программный способ:

```python
from tts_core import TtsConfig, get_jarvis_voice

# Получить настройки Джарвиса
jarvis = get_jarvis_voice("ru")  # или "en" для английского

config = TtsConfig(
    voice=jarvis.voice,
    rate=jarvis.rate,
    pitch=jarvis.pitch
)
```

## Тестирование

### Тест голоса Джарвиса:

```bash
cd backend
python test_jarvis_voice.py
```

Это создаст два файла:
- `jarvis_voice_en.wav` - английский вариант
- `jarvis_voice_ru.wav` - русский вариант

### Чат-бот с голосом Джарвиса:

```bash
cd backend
python test_jarvis_chatbot.py
```

Это создаст ответы с голосом Джарвиса на разные вопросы!

## Все доступные голоса

Система поддерживает множество пресетов:

- `jarvis` - Джарвис (английский)
- `jarvis_ru` - Джарвис (русский)
- `russian_male` - Русский мужской
- `russian_female` - Русский женский
- `assistant_male` - Ассистент (мужской)
- `assistant_female` - Ассистент (женский)
- `english_male_us` - Английский (США)
- `english_male_uk` - Английский (Великобритания)

### Просмотр всех голосов:

```python
from tts_core import list_available_voices

voices = list_available_voices()
for key, preset in voices.items():
    print(f"{key}: {preset.name} - {preset.description}")
```

## Настройка параметров

Если хочешь настроить голос более точно:

```python
from tts_core import TtsConfig

config = TtsConfig(
    provider="edge-tts",
    voice="ru-RU-DmitryNeural",
    rate="-15%",  # Еще медленнее
    pitch="-25Hz",  # Еще глубже
)
```

**Параметры:**
- `rate`: Скорость речи от -50% до +100%
- `pitch`: Высота тона от -50Hz до +50Hz

## Характеристики голоса Джарвиса

Голос Джарвиса отличается:
- ✅ **Глубокий мужской голос** - более низкий тон
- ✅ **Размеренная речь** - немного медленнее
- ✅ **Профессиональный стиль** - спокойный и интеллигентный
- ✅ **Чёткое произношение** - понятная речь

---

**Теперь у тебя есть голос Джарвиса!** 🎙️🤖✨

