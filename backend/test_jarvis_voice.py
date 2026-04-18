"""
Тест голоса Джарвиса.
Демонстрирует использование голоса в стиле Джарвиса из 'Железного человека'.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from tts_core import TtsEngine, TtsConfig, get_jarvis_voice, list_available_voices

def main():
    print("🎙️  Тест голоса Джарвиса (J.A.R.V.I.S.)")
    print("=" * 50)
    
    # Показываем доступные голоса
    print("\n📋 Доступные пресеты голосов:")
    voices = list_available_voices()
    for key, preset in voices.items():
        print(f"  • {key}: {preset.name} - {preset.description}")
    
    # Тест голоса Джарвиса (английский)
    print("\n" + "=" * 50)
    print("🇬🇧 Тест: Джарвис (английский, как в фильме)")
    print("=" * 50)
    
    jarvis_en = get_jarvis_voice("en")
    print(f"\nГолос: {jarvis_en.name}")
    print(f"ID: {jarvis_en.voice}")
    print(f"Скорость: {jarvis_en.rate}, Тон: {jarvis_en.pitch}")
    
    config_en = TtsConfig(
        provider="edge-tts",
        voice_preset="jarvis"  # Используем пресет
    )
    tts_en = TtsEngine(config=config_en)
    
    test_text_en = "Good morning, sir. I am J.A.R.V.I.S., your personal assistant. How may I help you today?"
    print(f"\n💬 Текст для озвучивания:\n{test_text_en}")
    print("\n🔊 Генерация голосового файла...")
    
    output_en = Path("jarvis_voice_en.wav")
    tts_en.synthesize_to_file(
        text=test_text_en,
        language="en",
        speaker=None,
        out_path=output_en
    )
    print(f"✅ Голосовой файл сохранён: {output_en}")
    
    # Тест голоса Джарвиса (русский)
    print("\n" + "=" * 50)
    print("🇷🇺 Тест: Джарвис (русский вариант)")
    print("=" * 50)
    
    jarvis_ru = get_jarvis_voice("ru")
    print(f"\nГолос: {jarvis_ru.name}")
    print(f"ID: {jarvis_ru.voice}")
    print(f"Скорость: {jarvis_ru.rate}, Тон: {jarvis_ru.pitch}")
    
    config_ru = TtsConfig(
        provider="edge-tts",
        voice_preset="jarvis_ru"
    )
    tts_ru = TtsEngine(config=config_ru)
    
    test_text_ru = "Доброе утро. Я ваш персональный ассистент. Чем могу помочь?"
    print(f"\n💬 Текст для озвучивания:\n{test_text_ru}")
    print("\n🔊 Генерация голосового файла...")
    
    output_ru = Path("jarvis_voice_ru.wav")
    tts_ru.synthesize_to_file(
        text=test_text_ru,
        language="ru",
        speaker=None,
        out_path=output_ru
    )
    print(f"✅ Голосовой файл сохранён: {output_ru}")
    
    print("\n" + "=" * 50)
    print("✅ Тест завершён!")
    print("=" * 50)
    print("\n💡 Открой файлы jarvis_voice_en.wav и jarvis_voice_ru.wav")
    print("   в аудио-плеере, чтобы услышать голос Джарвиса!")
    print("\n💡 Для использования в коде:")
    print("   from tts_core import TtsConfig")
    print("   config = TtsConfig(voice_preset='jarvis')  # или 'jarvis_ru'")

if __name__ == "__main__":
    main()

