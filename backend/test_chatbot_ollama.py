"""
Тест чат-бота с Ollama.
Демонстрирует работу всей системы: ASR + LLM (Ollama) + TTS
"""
import sys
from pathlib import Path

# Добавляем текущую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from llm_core import LlmEngine, LlmConfig
from chatbot import ChatBot, ChatBotConfig

def main():
    print("🚀 Тест чат-бота с Ollama")
    print("=" * 50)
    
    # Настройка LLM для Ollama
    print("⚙️  Настройка Ollama...")
    llm_config = LlmConfig(
        provider="ollama",
        model="qwen2.5:7b"  # Используем установленную модель
    )
    llm = LlmEngine(config=llm_config)
    
    # Создаём чат-бота с Ollama
    print("🤖 Создание чат-бота...")
    chatbot_config = ChatBotConfig(
        language="ru",
        llm_engine=llm
    )
    chatbot = ChatBot(config=chatbot_config)
    
    # Тестовые вопросы
    questions = [
        "Привет! Как дела?",
        "Что ты умеешь?",
        "Расскажи о себе"
    ]
    
    for question in questions:
        print(f"\n{'='*50}")
        print(f"❓ Вопрос: {question}")
        print("⏳ Обработка...")
        
        result = chatbot.process_text_question(
            question_text=question,
            output_audio_path=Path(f"answer_{questions.index(question)}.wav")
        )
        
        print(f"\n💬 Ответ: {result['answer_text']}")
        print(f"🔊 Аудио сохранено: {result['answer_audio']}")
    
    print(f"\n{'='*50}")
    print("✅ Тест завершён! Ollama успешно работает в чат-боте!")
    print("=" * 50)

if __name__ == "__main__":
    main()

