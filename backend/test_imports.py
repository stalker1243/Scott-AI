"""Простой тест импортов."""
import sys
from pathlib import Path

# Добавляем текущую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

print("Проверка импортов...")

try:
    from asr_core import get_default_asr_engine
    print("✅ ASR импортирован")
except Exception as e:
    print(f"❌ ASR ошибка: {e}")

try:
    from llm_core import get_default_llm_engine
    print("✅ LLM импортирован")
except Exception as e:
    print(f"❌ LLM ошибка: {e}")

try:
    from tts_core import get_default_engine
    print("✅ TTS импортирован")
except Exception as e:
    print(f"❌ TTS ошибка: {e}")

try:
    from chatbot import get_default_chatbot
    print("✅ ChatBot импортирован")
    
    # Пробуем создать экземпляр
    chatbot = get_default_chatbot()
    print("✅ ChatBot создан успешно")
except Exception as e:
    print(f"❌ ChatBot ошибка: {e}")
    import traceback
    traceback.print_exc()

print("\nВсе импорты проверены!")

