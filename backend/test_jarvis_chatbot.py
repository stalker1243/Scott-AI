"""
Чат-бот с голосом Джарвиса!
Использует голос в стиле J.A.R.V.I.S. из 'Железного человека'.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from llm_core import LlmEngine, LlmConfig
from tts_core import TtsEngine, TtsConfig
from knowledge_base import KnowledgeBase
from chatbot import ChatBot, ChatBotConfig

def main():
    print("🤖 ЧАТ-БОТ С ГОЛОСОМ ДЖАРВИСА")
    print("=" * 50)
    print("🎙️  Голос: J.A.R.V.I.S. (Jarvis)")
    print("=" * 50)
    
    # Настройка LLM с знаниями
    print("\n⚙️  Настройка Ollama...")
    knowledge_base = KnowledgeBase()
    llm_config = LlmConfig(provider="ollama", model="qwen2.5:7b")
    llm = LlmEngine(config=llm_config, knowledge_base=knowledge_base)
    
    # Настройка голоса Джарвиса
    print("🎙️  Настройка голоса Джарвиса...")
    # Можно выбрать:
    # - "jarvis" - английский (как в фильме)
    # - "jarvis_ru" - русский вариант
    tts_config = TtsConfig(
        provider="edge-tts",
        voice_preset="jarvis_ru"  # Русский вариант Джарвиса
    )
    tts = TtsEngine(config=tts_config)
    
    # Создаём чат-бота
    print("🤖 Создание чат-бота с голосом Джарвиса...")
    chatbot_config = ChatBotConfig(
        language="ru",
        llm_engine=llm,
        tts_engine=tts
    )
    chatbot = ChatBot(config=chatbot_config)
    
    # Тестовые вопросы
    questions = [
        "Расскажи о себе",
        "Кто такой Пётр I?",
        "Что такое фотосинтез?",
    ]
    
    print("\n" + "=" * 50)
    print("🎤 ВОПРОСЫ К ДЖАРВИСУ")
    print("=" * 50)
    
    for i, question in enumerate(questions, 1):
        print(f"\n{'='*50}")
        print(f"Вопрос {i}: {question}")
        print("-" * 50)
        
        result = chatbot.process_text_question(
            question_text=question,
            output_audio_path=Path(f"jarvis_answer_{i}.wav")
        )
        
        print(f"\n💬 Ответ Джарвиса:\n{result['answer_text']}")
        print(f"\n🔊 Голосовой файл: {result['answer_audio']}")
        print(f"💡 Открой {result['answer_audio']} чтобы услышать голос Джарвиса!")
    
    print(f"\n{'='*50}")
    print("✅ Диалог с Джарвисом завершён!")
    print("=" * 50)
    print("\n💡 Все ответы сохранены с голосом Джарвиса!")
    print("   Открой файлы jarvis_answer_*.wav в аудио-плеере")

if __name__ == "__main__":
    main()

