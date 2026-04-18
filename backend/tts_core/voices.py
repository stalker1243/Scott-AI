"""
Голоса для TTS - предустановленные настройки голосов.
"""
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class VoicePreset:
    """Пресет голоса."""
    name: str  # Название пресета
    voice: str  # ID голоса в edge-tts
    rate: str  # Скорость речи
    pitch: str  # Высота тона
    description: str  # Описание


# Предустановленные голоса
VOICE_PRESETS: Dict[str, VoicePreset] = {
    # Русские голоса
    "russian_female": VoicePreset(
        name="Русский женский",
        voice="ru-RU-SvetlanaNeural",
        rate="+6%",  # чуть быстрее по умолчанию
        pitch="+0Hz",
        description="Женский голос, стандартная настройка"
    ),
    "russian_male": VoicePreset(
        name="Русский мужской",
        voice="ru-RU-DmitryNeural",
        rate="+6%",  # чуть быстрее по умолчанию
        pitch="+0Hz",
        description="Мужской голос, стандартная настройка"
    ),
    
    # Джарвис-стиль голоса (английский, как в фильме)
    "jarvis": VoicePreset(
        name="Джарвис (J.A.R.V.I.S.)",
        voice="en-GB-RyanNeural",  # Британский мужской - похож на Джарвиса
        rate="0%",  # Нормальная скорость, ближе к фильму
        pitch="-15Hz",  # Немного ниже - более глубокий голос
        description="Голос в стиле Джарвиса из 'Железного человека' - британский мужской, спокойный, интеллигентный"
    ),
    "jarvis_ru": VoicePreset(
        name="Джарвис (русский)",
        voice="ru-RU-DmitryNeural",
        rate="+10%",  # немного быстрее, но комфортно
        pitch="-20Hz",  # Ниже - более глубокий голос
        description="Русский вариант голоса в стиле Джарвиса - глубокий мужской голос"
    ),

    # Гибрид: Джарвис + лёгкий робот (приятный, быстрый)
    "jarvis_robot_ru": VoicePreset(
        name="Джарвис‑робот (русский)",
        voice="ru-RU-DmitryNeural",
        rate="+22%",  # немного быстрее, оставаясь разборчивым
        pitch="+5Hz",  # Чуть выше, чтобы звучать легче
        description="Голос в стиле Джарвиса, но более быстрый и немного роботический, с приятным тоном"
    ),
    "scott_brutal_ru": VoicePreset(
        name="Скотт (брутальный ИИ)",
        voice="ru-RU-DmitryNeural",
        rate="+12%",
        pitch="-22Hz",
        description="Глубокий, собранный и профессиональный мужской голос ИИ-помощника"
    ),
    
    # Легкий роботический голос
    "robot_light": VoicePreset(
        name="Робот (лёгкий)",
        voice="ru-RU-DmitryNeural",
        rate="+10%",  # Немного быстрее - более динамично
        pitch="+15Hz",  # Выше - более лёгкий и "роботический" звук
        description="Лёгкий роботический голос - высокий, быстрый, похож на робота"
    ),
    "robot_light_female": VoicePreset(
        name="Робот (лёгкий, женский)",
        voice="ru-RU-SvetlanaNeural",
        rate="+15%",  # Быстрее
        pitch="+20Hz",  # Выше - более лёгкий звук
        description="Лёгкий роботический женский голос"
    ),
    
    # Другие интересные варианты
    "assistant_male": VoicePreset(
        name="Ассистент (мужской)",
        voice="ru-RU-DmitryNeural",
        rate="+0%",
        pitch="-10Hz",
        description="Профессиональный мужской голос ассистента"
    ),
    "assistant_female": VoicePreset(
        name="Ассистент (женский)",
        voice="ru-RU-SvetlanaNeural",
        rate="+0%",
        pitch="+0Hz",
        description="Профессиональный женский голос ассистента"
    ),

    # Ролевые голоса (временные пресеты по ролям/возрасту)
    "ru_kid_boy": VoicePreset(
        name="Мальчик (ребёнок)",
        voice="ru-RU-DmitryNeural",
        rate="+18%",
        pitch="+18Hz",
        description="Весёлый голос мальчика, быстрый и высокий"
    ),
    "ru_kid_girl": VoicePreset(
        name="Девочка (ребёнок)",
        voice="ru-RU-SvetlanaNeural",
        rate="+18%",
        pitch="+20Hz",
        description="Лёгкий голос девочки, быстрый и высокий"
    ),
    "ru_teen_boy": VoicePreset(
        name="Мальчик (подросток)",
        voice="ru-RU-DmitryNeural",
        rate="+10%",
        pitch="+8Hz",
        description="Более молодой мужской голос, немного быстрее и выше"
    ),
    "ru_teen_girl": VoicePreset(
        name="Девочка (подросток)",
        voice="ru-RU-SvetlanaNeural",
        rate="+10%",
        pitch="+10Hz",
        description="Женский голос в стиле подростка, более живой и высокий"
    ),
    "ru_man": VoicePreset(
        name="Мужчина",
        voice="ru-RU-DmitryNeural",
        rate="+0%",
        pitch="-12Hz",
        description="Спокойный взрослый мужской голос"
    ),
    "ru_woman": VoicePreset(
        name="Женщина",
        voice="ru-RU-SvetlanaNeural",
        rate="+0%",
        pitch="-4Hz",
        description="Спокойный взрослый женский голос"
    ),
    "ru_grandpa": VoicePreset(
        name="Дедушка",
        voice="ru-RU-DmitryNeural",
        rate="-10%",
        pitch="-24Hz",
        description="Более медленный и низкий голос, стиль «дедушка»"
    ),
    "ru_grandma": VoicePreset(
        name="Бабушка",
        voice="ru-RU-SvetlanaNeural",
        rate="-10%",
        pitch="-18Hz",
        description="Мягкий, чуть более низкий голос в стиле «бабушка»"
    ),
    
    # Английские голоса
    "english_male_us": VoicePreset(
        name="Английский (США, мужской)",
        voice="en-US-GuyNeural",
        rate="+0%",
        pitch="+0Hz",
        description="Американский мужской голос"
    ),
    "english_male_uk": VoicePreset(
        name="Английский (Великобритания, мужской)",
        voice="en-GB-RyanNeural",
        rate="+0%",
        pitch="+0Hz",
        description="Британский мужской голос"
    ),
}


def get_voice_preset(preset_name: str) -> Optional[VoicePreset]:
    """
    Получить пресет голоса по имени.
    
    Args:
        preset_name: Название пресета (jarvis, russian_male, и т.д.)
        
    Returns:
        VoicePreset или None если не найден
    """
    return VOICE_PRESETS.get(preset_name.lower())


def list_available_voices() -> Dict[str, VoicePreset]:
    """Возвращает все доступные пресеты голосов."""
    return VOICE_PRESETS.copy()


def get_jarvis_voice(language: str = "en") -> VoicePreset:
    """
    Получить голос Джарвиса для указанного языка.
    
    Args:
        language: "en" для английского, "ru" для русского
        
    Returns:
        VoicePreset для Джарвиса
    """
    if language.lower() == "ru":
        return VOICE_PRESETS["jarvis_ru"]
    else:
        return VOICE_PRESETS["jarvis"]


def get_robot_light_voice(gender: str = "male") -> VoicePreset:
    """
    Получить лёгкий роботический голос.
    
    Args:
        gender: "male" для мужского, "female" для женского
        
    Returns:
        VoicePreset для роботического голоса
    """
    if gender.lower() == "female":
        return VOICE_PRESETS["robot_light_female"]
    else:
        return VOICE_PRESETS["robot_light"]

