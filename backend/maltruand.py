#!/usr/bin/env python3
"""
Скотт (Scott) - Голосовой ассистент с искусственным интеллектом.

Запуск: scott
Или: python maltruand.py
"""
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    from .llm_core import LlmEngine, LlmConfig
    from .tts_core import TtsEngine, TtsConfig
    from .knowledge_base import KnowledgeBase
    from .chatbot import ChatBot, ChatBotConfig
    from .system_control import SystemController
    from .config_store import load_config
    from .audio_playback import play_audio
except ImportError:
    from llm_core import LlmEngine, LlmConfig
    from tts_core import TtsEngine, TtsConfig
    from knowledge_base import KnowledgeBase
    from chatbot import ChatBot, ChatBotConfig
    from system_control import SystemController
    from config_store import load_config
    from audio_playback import play_audio


def print_banner():
    """Выводит приветственный баннер."""
    banner = """
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║              🎙️  СКОТТ (Scott)  🤖                      ║
║                                                           ║
║     Голосовой ассистент с искусственным интеллектом      ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
"""
    print(banner)


def initialize_scott():
    """Инициализирует Скотта."""
    print("⚙️  Инициализация Скотта...")

    app_cfg = load_config()
    
    # Настройка LLM с знаниями
    knowledge_base = KnowledgeBase()
    llm_config = LlmConfig(
        provider=app_cfg.llm_provider,
        model=app_cfg.llm_model,
        temperature=float(getattr(app_cfg, "llm_temperature", 0.4)),
        max_tokens=int(getattr(app_cfg, "llm_max_tokens", 160)),
    )
    llm = LlmEngine(config=llm_config, knowledge_base=knowledge_base)
    
    # Настройка голоса
    voice_by_gender = {
        "male": "scott_brutal_ru",
        "female": "robot_light_female",
    }
    selected_voice = app_cfg.voice_preset or voice_by_gender.get(app_cfg.preferred_voice_gender, "scott_brutal_ru")
    # Используем гибридный голос: стиль Джарвиса + лёгкий робот,
    # быстрый и приятный для повседневной речи
    tts_config = TtsConfig(voice_preset=selected_voice)
    tts = TtsEngine(config=tts_config)
    
    # Создание чат-бота
    chatbot_config = ChatBotConfig(
        language="ru",
        llm_engine=llm,
        tts_engine=tts,
        memory_path=Path(app_cfg.memory_path),
    )
    chatbot = ChatBot(config=chatbot_config)

    # Контроллер системы (для команд ОС)
    chatbot.system_controller = SystemController(
        offline_game_limit_minutes=app_cfg.offline_game_limit_minutes,
        advice_cooldown_minutes=app_cfg.activity_advice_cooldown_minutes,
        enable_power_confirmation=app_cfg.enable_power_confirmation,
        memory_path=Path(app_cfg.assistant_memory_path),
        user_name=app_cfg.user_name,
        user_title=app_cfg.user_title,
    )

    print("✅ Скотт готов к работе!\n")
    return chatbot


def greet_user(chatbot):
    """Приветствие пользователя."""
    app_cfg = load_config()
    who = app_cfg.user_name or app_cfg.user_title or "сэр"
    greeting = f"Здравствуйте, {who}! Я Скотт, ваш голосовой ассистент. Чем могу помочь?"
    print(f"\n🎙️  Скотт: {greeting}\n")
    
    # Озвучиваем приветствие
    audio_path = Path("scott_greeting.wav")
    try:
        chatbot.tts.synthesize_to_file(
            text=greeting,
            language="ru",
            speaker=None,
            out_path=audio_path
        )
        print(f"💡 🔊 Приветствие сохранено: {audio_path}")

        if play_audio(audio_path):
            print("🔊 Приветствие воспроизводится...")
    except Exception as e:
        print(f"⚠️  Не удалось озвучить приветствие: {e}")


def main_loop(chatbot):
    """Основной цикл взаимодействия."""
    print("─" * 60)
    print("💡 Введите ваш вопрос (или 'выход' / 'exit' для завершения)")
    print("─" * 60)
    
    conversation_count = 0
    
    while True:
        try:
            sys_controller = getattr(chatbot, "system_controller", None)
            if sys_controller is not None:
                advice = sys_controller.poll_activity()
                if advice and advice.message:
                    print(f"\n🎙️  Скотт: {advice.message}")
                    audio_path = Path(f"scott_advice_{conversation_count}.wav")
                    chatbot.tts.synthesize_to_file(text=advice.message, language="ru", speaker=None, out_path=audio_path)
                    play_audio(audio_path)

            # Получаем вопрос от пользователя
            user_input = input("\n👤 Вы: ").strip()
            
            # Проверка на выход
            if user_input.lower() in ['выход', 'exit', 'quit', 'q', 'стоп']:
                print("\n👋 Скотт: До свидания! Было приятно пообщаться!")
                break
            
            if not user_input:
                print("💡 Введите вопрос, пожалуйста.")
                continue
            
            conversation_count += 1

            # Проверяем, является ли это командой для ОС
            sys_controller = getattr(chatbot, "system_controller", None)
            if sys_controller is not None:
                sys_result = sys_controller.handle_command(user_input)
                if sys_result.handled:
                    # Отвечаем текстом и голосом без обращения к LLM
                    response_text = sys_result.message or "Команда выполнена."
                    print(f"\n🖥️  Система: {response_text}")

                    audio_path = Path(f"scott_system_{conversation_count}.wav")
                    try:
                        chatbot.tts.synthesize_to_file(
                            text=response_text,
                            language="ru",
                            speaker=None,
                            out_path=audio_path,
                        )
                        play_audio(audio_path)
                    except Exception as e:
                        print(f"⚠️  Не удалось озвучить системный ответ: {e}")

                    # Переходим к следующему вопросу
                    continue
            
            # Обрабатываем вопрос
            print(f"\n🤖 Обработка вопроса {conversation_count}...")
            
            audio_path = Path(f"scott_answer_{conversation_count}.wav")
            result = chatbot.process_text_question(
                question_text=user_input,
                output_audio_path=audio_path,
            )
            
            # Выводим ответ
            print(f"\n🎙️  Скотт: {result['answer_text']}")

            # Воспроизведение без запуска внешнего плеера.
            if not play_audio(audio_path):
                print("⚠️  Не удалось воспроизвести ответ.")
            
        except KeyboardInterrupt:
            print("\n\n👋 Скотт: Прервано пользователем. До свидания!")
            break
        except Exception as e:
            print(f"\n❌ Ошибка: {e}")
            print("💡 Попробуйте ещё раз или введите 'выход' для завершения.")


def main():
    """Главная функция."""
    print_banner()
    
    try:
        # Инициализация
        chatbot = initialize_scott()
        
        # Приветствие
        greet_user(chatbot)
        
        # Основной цикл
        main_loop(chatbot)
        
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

