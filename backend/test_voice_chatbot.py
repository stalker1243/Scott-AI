"""
Тест чат-бота с голосовыми ответами и знаниями.
Демонстрирует работу: вопрос → LLM с знаниями → голосовой ответ
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from llm_core import LlmEngine, LlmConfig
from tts_core import TtsEngine, TtsConfig
from knowledge_base import KnowledgeBase
from chatbot import ChatBot, ChatBotConfig

def main():
    print("🎙️  Тест чат-бота с ГОЛОСОМ и ЗНАНИЯМИ")
    print("=" * 50)
    
    # Настройка LLM с Ollama
    print("⚙️  Настройка Ollama...")
    llm_config = LlmConfig(provider="ollama", model="qwen2.5:7b")
    
    # Добавляем базу знаний
    print("📚 Загрузка базы знаний...")
    knowledge_base = KnowledgeBase()
    llm = LlmEngine(config=llm_config, knowledge_base=knowledge_base)
    
    # Настройка TTS с edge-tts
    print("🔊 Настройка голоса (Edge-TTS)...")
    tts_config = TtsConfig(provider="edge-tts", voice="ru-RU-SvetlanaNeural")
    tts = TtsEngine(config=tts_config)
    
    # Создаём чат-бота
    print("🤖 Создание чат-бота...")
    chatbot_config = ChatBotConfig(
        language="ru",
        llm_engine=llm,
        tts_engine=tts
    )
    chatbot = ChatBot(config=chatbot_config)
    
    # Тестовые вопросы из разных областей
    questions = [
        "Расскажи о Пушкине",
        "Кто такой Пётр I?",
        "Почему небо голубое?",
        "Что такое фотосинтез?",
        "Расскажи о Москве",
    ]
    
    print("\n" + "=" * 50)
    print("🎤 ГОЛОСОВЫЕ ОТВЕТЫ С ЗНАНИЯМИ")
    print("=" * 50)
    
    for i, question in enumerate(questions, 1):
        print(f"\n{'='*50}")
        print(f"Вопрос {i}/{len(questions)}: {question}")
        print("-" * 50)
        
        result = chatbot.process_text_question(
            question_text=question,
            output_audio_path=Path(f"voice_answer_{i}.wav")
        )
        
        print(f"\n💬 Текст ответа:\n{result['answer_text']}")
        print(f"\n🔊 Голосовой файл: {result['answer_audio']}")
        print(f"💡 Открой файл {result['answer_audio']} в плеере, чтобы услышать голосовой ответ!")
    
    print(f"\n{'='*50}")
    print("✅ Тест завершён!")
    print("=" * 50)
    print("\n💡 Все голосовые ответы сохранены в файлы voice_answer_*.wav")
    print("   Открой их в любом аудио-плеере, чтобы услышать голосовые ответы!")

if __name__ == "__main__":
    main()

