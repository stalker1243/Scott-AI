"""
Простой локальный скрипт для теста TTS-ядра без сервера.

Запуск из папки backend:
    python cli_tts_local.py --text "Привет, мир" --language ru --out out.wav
"""

import argparse
from pathlib import Path

from tts_core import get_default_engine


def main() -> None:
    parser = argparse.ArgumentParser(description="Локальный тест TTS-ядра")
    parser.add_argument("--text", type=str, required=True, help="Текст для озвучки")
    parser.add_argument("--language", type=str, default="ru", help="Язык (пока не используется)")
    parser.add_argument("--speaker", type=str, default=None, help="Идентификатор голоса (пока не используется)")
    parser.add_argument("--out", type=str, default="out.wav", help="Путь к выходному WAV-файлу")

    args = parser.parse_args()

    engine = get_default_engine()
    out_path = Path(args.out)

    engine.synthesize_to_file(
        text=args.text,
        language=args.language,
        speaker=args.speaker,
        out_path=out_path,
    )

    print(f"✅ Аудио сгенерировано: {out_path.resolve()}")


if __name__ == "__main__":
    main()


