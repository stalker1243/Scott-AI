"""
Тест подключения Ollama.
Запусти этот скрипт, чтобы проверить, что Ollama правильно настроен.
"""
import sys
from pathlib import Path

# Добавляем текущую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from llm_core import LlmEngine, LlmConfig

def main():
    print("🔍 Проверка Ollama...")
    print("=" * 50)
    
    # Проверяем доступность Ollama сервера
    models = []
    try:
        import requests
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=2)
            if response.status_code == 200:
                models_data = response.json()
                models = models_data.get("models", [])
                print(f"✅ Ollama сервер работает!")
                if models:
                    model_names = [m.get("name", "?") for m in models]
                    print(f"📦 Установленные модели: {', '.join(model_names)}")
                else:
                    print("⚠️  Модели не найдены. Установите модель: ollama run qwen2.5:7b")
                    return
            else:
                print(f"❌ Ollama сервер отвечает с ошибкой: {response.status_code}")
                return
        except requests.exceptions.ConnectionError:
            print("❌ Ollama сервер не запущен!")
            print("\n💡 Установите и запустите Ollama:")
            print("   1. Скачайте: https://ollama.ai/download")
            print("   2. Установите Ollama")
            print("   3. Запустите модель: ollama run qwen2.5:7b")
            return
        except requests.exceptions.Timeout:
            print("❌ Ollama сервер не отвечает (таймаут)")
            return
    except ImportError:
        print("❌ Библиотека requests не установлена")
        print("💡 Установите: pip install requests")
        return
    
    print("\n🚀 Инициализация LLM движка с Ollama...")
    
    # Используем первую доступную модель из списка установленных
    if models:
        model_found = models[0].get("name", "")
        print(f"✅ Используем модель: {model_found}")
    else:
        print("⚠️  Модели не найдены")
        print("💡 Установите модель: ollama run qwen2.5:7b")
        print("   или: ollama run llama3.2")
        return
    
    config = LlmConfig(provider="ollama", model=model_found)
    llm = LlmEngine(config=config)
    
    print(f"\n💬 Тестовый вопрос: 'Привет! Как дела?'")
    print("⏳ Ожидание ответа (это может занять несколько секунд)...")
    
    try:
        answer = llm.answer("Привет! Как дела?")
        
        print(f"\n🤖 Ответ Ollama:\n{answer}")
        print("\n" + "=" * 50)
        print("✅ Если ты видишь разумный ответ выше, Ollama работает правильно!")
        print("=" * 50)
    except Exception as e:
        print(f"\n❌ Ошибка при получении ответа: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

