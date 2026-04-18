"""
Голосовой режим Скотта в реальном времени.

Цикл:
- записываем речь с микрофона
- распознаём (ASR)
- получаем ответ (LLM)
- озвучиваем (TTS)

Запуск:
    cd backend
    python voice_chat_live.py
"""
import os
import sys
from pathlib import Path
from typing import Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import sounddevice as sd
import soundfile as sf
import numpy as np


try:
    from .chatbot import ChatBot, ChatBotConfig  # noqa: E402
    from .asr_core import AsrEngine, AsrConfig  # noqa: E402
    from .llm_core import LlmEngine, LlmConfig  # noqa: E402
    from .knowledge_base import KnowledgeBase  # noqa: E402
    from .tts_core import TtsEngine, TtsConfig  # noqa: E402
    from .config_store import load_config  # noqa: E402
    from .audio_playback import play_audio  # noqa: E402
except ImportError:
    from chatbot import ChatBot, ChatBotConfig  # noqa: E402
    from asr_core import AsrEngine, AsrConfig  # noqa: E402
    from llm_core import LlmEngine, LlmConfig  # noqa: E402
    from knowledge_base import KnowledgeBase  # noqa: E402
    from tts_core import TtsEngine, TtsConfig  # noqa: E402
    from config_store import load_config  # noqa: E402
    from audio_playback import play_audio  # noqa: E402


SAMPLE_RATE = 16000
CHANNELS = 1


def _pick_input_device() -> Optional[int]:
    """
    Выбор микрофона.
    Если в системе default input == -1, выбираем первый доступный.
    Можно задать переменную окружения MALTRUAND_INPUT_DEVICE (число).
    """
    env = os.getenv("MALTRUAND_INPUT_DEVICE")
    if env is not None and env.strip().isdigit():
        return int(env.strip())

    try:
        default_in, _ = sd.default.device  # type: ignore[attr-defined]
    except Exception:
        default_in = None

    if isinstance(default_in, int) and default_in >= 0:
        return default_in

    try:
        devices = sd.query_devices()
        for i, d in enumerate(devices):
            if d.get("max_input_channels", 0) > 0:
                return i
    except Exception:
        return None

    return None


def record_audio(output_path: Path, duration: Optional[float] = None) -> None:
    """
    Запись звука с микрофона.

    Если duration задана — пишем фиксированное время.
    Если нет — пишем до 8–10 секунд и автоматически обрезаем тишину
    в начале и в конце (простая VAD‑логика).
    """
    if duration is None:
        max_duration = 10.0  # секунд, чтобы не записывать слишком долго
        silence_threshold = 0.015  # порог "тишины"
        min_duration = 0.5  # минимальная длина фразы, секунд

        print("🎤 Нажми Enter, скажи фразу, и просто замолчи — запись остановится автоматически.")
        input("▶ Нажми Enter для начала записи...")
        print("🔴 Идёт запись... говори.")

        # Пишем фиксированный буфер и потом обрезаем тишину по краям
        device = _pick_input_device()
        audio = sd.rec(
            int(max_duration * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            device=device,
        )
        sd.wait()

        # Обрезаем тишину
        mono = audio.reshape(-1)
        energy = np.abs(mono)
        non_silent = np.where(energy > silence_threshold)[0]

        if len(non_silent) == 0:
            print("⚠️ Похоже, я ничего не услышал. Попробуй ещё раз говорить чуть громче.")
            return

        start_idx = max(non_silent[0] - int(0.1 * SAMPLE_RATE), 0)
        end_idx = min(non_silent[-1] + int(0.4 * SAMPLE_RATE), len(mono) - 1)

        trimmed = mono[start_idx:end_idx]
        if len(trimmed) < int(min_duration * SAMPLE_RATE):
            # Если фраза очень короткая, всё равно сохраняем как есть
            trimmed = mono[: int(min_duration * SAMPLE_RATE)]

        sf.write(str(output_path), trimmed, SAMPLE_RATE)
    else:
        print(f"🔴 Запись {duration} секунд...")
        device = _pick_input_device()
        audio = sd.rec(
            int(duration * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            device=device,
        )
        sd.wait()
        sf.write(str(output_path), audio, SAMPLE_RATE)

    print(f"✅ Запись сохранена: {output_path}")


def init_chatbot() -> ChatBot:
    """Инициализация чатбота для голосового режима."""
    print("⚙️  Инициализация голосового Скотта...")
    app_cfg = load_config()
    kb = KnowledgeBase()
    llm_cfg = LlmConfig(provider=app_cfg.llm_provider, model=app_cfg.llm_model)
    llm = LlmEngine(config=llm_cfg, knowledge_base=kb)

    # Используем тот же голосовой профиль, что и в основном CLI-режиме.
    # (Джарвис + лёгкий робот, быстрая приятная речь)
    tts_cfg = TtsConfig(voice_preset=app_cfg.voice_preset)
    tts = TtsEngine(config=tts_cfg)

    asr = AsrEngine(AsrConfig(model_size=app_cfg.asr_model_size, language=app_cfg.asr_language, device=app_cfg.asr_device))

    cfg = ChatBotConfig(
        language="ru",
        asr_engine=asr,
        llm_engine=llm,
        tts_engine=tts,
        memory_path=Path(app_cfg.memory_path),
    )
    bot = ChatBot(config=cfg)
    print("✅ Голосовой Скотт готов!\n")
    return bot


def main():
    bot = init_chatbot()
    tmp_dir = Path("./voice_sessions")
    tmp_dir.mkdir(exist_ok=True)

    print("🎙️  ГОЛОСОВОЙ РЕЖИМ МАЛЬТРУАНТА")
    print("─" * 60)
    print("Режимы:")
    print("1) Смешанный: текст + голос. Enter → говорить → замолчать → ответ.")
    print("2) Непрерывный голос: Скотт слушает, отвечает и сразу снова слушает.")
    print("   (остановка через Ctrl+C в терминале)")
    print("─" * 60)

    mode = input("Выбери режим (1 или 2, по умолчанию 1): ").strip()
    if mode == "2":
        # Непрерывный голосовой режим
        counter = 0
        print("\n🎧 Непрерывный голосовой режим включён.")
        print("Говори фразу после подсказки, замолчи — и жди ответ Скотта.")
        print("Чтобы завершить, нажми Ctrl+C в терминале.\n")
        while True:
            try:
                counter += 1
                question_path = tmp_dir / f"voice_question_auto_{counter}.wav"
                answer_path = tmp_dir / f"voice_answer_auto_{counter}.wav"

                record_audio(question_path, duration=None)

                print("🤖 Обработка голосового вопроса...")
                result = bot.process_audio_question(question_path, output_audio_path=answer_path)

                print(f"\n📝 Распознанный текст вопроса: {result['question_text']}")
                print(f"🎙️  Скотт: {result['answer_text']}")

                play_audio(answer_path)
            except KeyboardInterrupt:
                print("\n\n👋 Скотт: Непрерывный голосовой режим остановлен. До свидания!")
                break
            except Exception as e:
                print(f"\n❌ Ошибка: {e}")
                print("💡 Попробуй ещё раз произнести фразу.")
        return

    # Режим 1: смешанный (как раньше)
    print("\n🔁 Включён смешанный режим: текст + голос.")
    counter = 0
    while True:
        try:
            text_cmd = input("\n👤 (текст или просто Enter для голосового вопроса): ").strip().lower()

            if text_cmd in ("выход", "exit", "quit", "q", "стоп"):
                print("\n👋 Скотт: До свидания! Было приятно пообщаться!")
                break

            if text_cmd:
                # Обычный текстовый вопрос
                counter += 1
                answer_path = tmp_dir / f"voice_answer_text_{counter}.wav"
                result = bot.process_text_question(text_cmd, output_audio_path=answer_path)
                print(f"\n🎙️  Скотт: {result['answer_text']}")
                play_audio(answer_path)
                continue

            # Голосовой вопрос
            counter += 1
            question_path = tmp_dir / f"voice_question_{counter}.wav"
            answer_path = tmp_dir / f"voice_answer_{counter}.wav"

            record_audio(question_path, duration=None)

            print("🤖 Обработка голосового вопроса...")
            result = bot.process_audio_question(question_path, output_audio_path=answer_path)

            print(f"\n📝 Распознанный текст вопроса: {result['question_text']}")
            print(f"🎙️  Скотт: {result['answer_text']}")

            play_audio(answer_path)

        except KeyboardInterrupt:
            print("\n\n👋 Скотт: Прервано пользователем. До свидания!")
            break
        except Exception as e:
            print(f"\n❌ Ошибка: {e}")
            print("💡 Попробуй ещё раз или введи 'выход' для завершения.")


if __name__ == "__main__":
    main()


