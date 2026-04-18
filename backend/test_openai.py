"""
Тест подключения OpenAI API.
Запусти этот скрипт, чтобы проверить, что OpenAI правильно настроен.
"""
import os
import sys
from pathlib import Path

# Добавляем текущую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from llm_core import LlmEngine, LlmConfig

def main():
    print("🔍 Проверка настроек OpenAI...")
    print("=" * 50)
    
    # Проверяем наличие ключа
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        print(f"✅ API ключ найден: {api_key[:10]}...{api_key[-4:]}")
    else:
        print("❌ API ключ не найден в переменных окружения")
        print("\n💡 Установите ключ одним из способов:")
        print("   1. PowerShell: $env:OPENAI_API_KEY='sk-твой-ключ'")
        print("   2. CMD: set OPENAI_API_KEY=sk-твой-ключ")
        print("   3. Создайте файл .env с OPENAI_API_KEY=sk-твой-ключ")
        return
    
    print("\n🚀 Инициализация LLM движка...")
    config = LlmConfig(provider="openai", model="gpt-3.5-turbo")
    llm = LlmEngine(config=config)
    
    print("\n💬 Тестовый вопрос: 'Привет! Как дела?'")
    answer = llm.answer("Привет! Как дела?")
    
    print(f"\n🤖 Ответ OpenAI:\n{answer}")
    print("\n" + "=" * 50)
    print("✅ Если ты видишь разумный ответ выше, OpenAI работает правильно!")
    print("=" * 50)

if __name__ == "__main__":
    main()

