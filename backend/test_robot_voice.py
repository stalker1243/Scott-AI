"""
Тест лёгкого роботического голоса.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from tts_core import TtsEngine, TtsConfig, get_robot_light_voice, list_available_voices

def main():
    print("🤖 Тест лёгкого роботического голоса")
    print("=" * 50)
    
    # Показываем доступные роботические голоса
    print("\n📋 Доступные роботические голоса:")
    robot_male = get_robot_light_voice("male")
    robot_female = get_robot_light_voice("female")
    
    print(f"  • Мужской: {robot_male.name}")
    print(f"    - {robot_male.description}")
    print(f"    - Скорость: {robot_male.rate}, Тон: {robot_male.pitch}")
    
    print(f"\n  • Женский: {robot_female.name}")
    print(f"    - {robot_female.description}")
    print(f"    - Скорость: {robot_female.rate}, Тон: {robot_female.pitch}")
    
    # Тест мужского роботического голоса
    print("\n" + "=" * 50)
    print("🤖 Тест: Робот (лёгкий, мужской)")
    print("=" * 50)
    
    config_male = TtsConfig(voice_preset="robot_light")
    tts_male = TtsEngine(config=config_male)
    
    test_text = "Здравствуйте! Я Мальтруант, ваш робот-ассистент. Чем могу помочь?"
    print(f"\n💬 Текст для озвучивания:\n{test_text}")
    print("\n🔊 Генерация голосового файла...")
    
    output_male = Path("robot_voice_male.wav")
    tts_male.synthesize_to_file(
        text=test_text,
        language="ru",
        speaker=None,
        out_path=output_male
    )
    print(f"✅ Голосовой файл сохранён: {output_male}")
    
    # Тест женского роботического голоса
    print("\n" + "=" * 50)
    print("🤖 Тест: Робот (лёгкий, женский)")
    print("=" * 50)
    
    config_female = TtsConfig(voice_preset="robot_light_female")
    tts_female = TtsEngine(config=config_female)
    
    print(f"\n💬 Текст для озвучивания:\n{test_text}")
    print("\n🔊 Генерация голосового файла...")
    
    output_female = Path("robot_voice_female.wav")
    tts_female.synthesize_to_file(
        text=test_text,
        language="ru",
        speaker=None,
        out_path=output_female
    )
    print(f"✅ Голосовой файл сохранён: {output_female}")
    
    print("\n" + "=" * 50)
    print("✅ Тест завершён!")
    print("=" * 50)
    print("\n💡 Открой файлы robot_voice_male.wav и robot_voice_female.wav")
    print("   в аудио-плеере, чтобы услышать роботические голоса!")
    print("\n💡 Для использования в Мальтруанте:")
    print("   В файле maltruand.py уже установлен голос 'robot_light'")

if __name__ == "__main__":
    main()

