"""
Локальный тест чат-бота без сервера.
Можно тестировать всю систему: ASR + LLM + TTS
"""
import argparse
import sys
from pathlib import Path

# Добавляем текущую директорию в путь для импортов
sys.path.insert(0, str(Path(__file__).parent))

from chatbot import get_default_chatbot


def main():
    parser = argparse.ArgumentParser(description="Тест чат-бота локально")
    parser.add_argument(
        "--text",
        type=str,
        help="Текст вопроса (если не указан --audio)"
    )
    parser.add_argument(
        "--audio",
        type=str,
        help="Путь к аудиофайлу с вопросом"
    )
    parser.add_argument(
        "--out",
        type=str,
        default="answer.wav",
        help="Путь для сохранения аудио ответа (по умолчанию: answer.wav)"
    )
    parser.add_argument(
        "--language",
        type=str,
        default="ru",
        help="Язык (по умолчанию: ru)"
    )

    args = parser.parse_args()

    # Создаём чат-бота
    print("🚀 Инициализация чат-бота...")
    chatbot = get_default_chatbot()

    # Обрабатываем вопрос
    if args.audio:
        # Из аудио
        audio_path = Path(args.audio)
        if not audio_path.exists():
            print(f"❌ Файл не найден: {audio_path}")
            return
        
        result = chatbot.process_audio_question(
            audio_path=audio_path,
            output_audio_path=Path(args.out)
        )
    elif args.text:
        # Из текста
        result = chatbot.process_text_question(
            question_text=args.text,
            output_audio_path=Path(args.out)
        )
    else:
        print("❌ Укажите --text или --audio")
        parser.print_help()
        return

    # Выводим результаты
    print("\n" + "=" * 50)
    print("📊 РЕЗУЛЬТАТЫ:")
    print("=" * 50)
    print(f"❓ Вопрос: {result['question_text']}")
    print(f"💬 Ответ: {result['answer_text']}")
    print(f"🔊 Аудио: {result['answer_audio']}")
    print("=" * 50)


if __name__ == "__main__":
    main()

