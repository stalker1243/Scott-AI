"""
Локальный синтез речи через Silero TTS.

Зачем: до этого Scott говорил через edge-tts — это сетевой запрос к серверам
Microsoft, ~1.9с на фразу и полная неработоспособность без интернета. Замеры
(GET /timings) показали, что после переезда распознавания речи на видеокарту
именно синтез стал самым долгим этапом голосового цикла.

Silero работает локально на той же RTX 3060: модель весит ~38 МБ, прогретый
синтез короткой фразы занимает около 15 мс. Скачивается один раз через
torch.hub, дальше работает офлайн.

Голоса модели v4_ru: aidar, eugene (мужские), baya, kseniya, xenia (женские).
"""

import os
import threading
from pathlib import Path
from typing import Optional

# Голоса, которые умеет модель v4_ru, с человекочитаемыми подписями для UI.
SILERO_VOICES = {
    "aidar": "Айдар (муж., Silero, локальный)",
    "eugene": "Евгений (муж., Silero, локальный)",
    "baya": "Бая (жен., Silero, локальный)",
    "kseniya": "Ксения (жен., Silero, локальный)",
    "xenia": "Ксения X (жен., Silero, локальный)",
}

# Пол голоса — нужен, чтобы лаунчер мог показывать, например, только мужские.
SILERO_VOICE_GENDERS = {
    "aidar": "male",
    "eugene": "male",
    "baya": "female",
    "kseniya": "female",
    "xenia": "female",
}

DEFAULT_SILERO_VOICE = os.getenv("SILERO_VOICE", "aidar")
# 48000 — максимальное качество модели; 24000 звучит чуть глуше, но файл вдвое меньше.
SAMPLE_RATE = int(os.getenv("SILERO_SAMPLE_RATE", "48000"))

_model = None
_model_device = None
_load_lock = threading.Lock()


def _resolve_device() -> str:
    """Видеокарта, если доступна, иначе процессор. Переопределяется SILERO_DEVICE."""
    forced = os.getenv("SILERO_DEVICE", "").strip().lower()
    if forced in ("cpu", "cuda"):
        return forced
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def is_available() -> bool:
    """Можно ли вообще использовать Silero (есть torch и omegaconf)."""
    try:
        import importlib.util
        return all(importlib.util.find_spec(m) for m in ("torch", "omegaconf"))
    except Exception:
        return False


def get_model():
    """
    Лениво загрузить модель один раз на процесс. Первый вызов скачивает ~38 МБ
    (только если модели ещё нет в кэше torch.hub) и занимает несколько секунд,
    дальнейшие — мгновенные.
    """
    global _model, _model_device
    if _model is not None:
        return _model

    with _load_lock:
        if _model is not None:  # мог загрузиться, пока ждали блокировку
            return _model

        import torch

        device = _resolve_device()
        print(f"🎙️ Загружаю Silero TTS (v4_ru) на {device.upper()}...")
        model, _ = torch.hub.load(
            repo_or_dir="snakers4/silero-models",
            model="silero_tts",
            language="ru",
            speaker="v4_ru",
            trust_repo=True,
        )
        model.to(torch.device(device))
        _model = model
        _model_device = device
        print(f"✅ Silero TTS готов на {device.upper()} (голоса: {', '.join(SILERO_VOICES)})")
        return _model


def synthesize(text: str, out_path: str, voice: Optional[str] = None) -> Optional[str]:
    """
    Синтезировать речь в WAV-файл. Возвращает путь к файлу или None при ошибке.

    Ошибку намеренно не пробрасываем: вызывающий код (ScottVoice.speak_to_file)
    по None откатывается на edge-tts, чтобы Scott не онемел из-за сбоя одного движка.
    """
    voice = voice or DEFAULT_SILERO_VOICE
    if voice not in SILERO_VOICES:
        print(f"⚠️ Неизвестный голос Silero «{voice}», беру {DEFAULT_SILERO_VOICE}")
        voice = DEFAULT_SILERO_VOICE

    try:
        model = get_model()
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        model.save_wav(
            text=text,
            speaker=voice,
            sample_rate=SAMPLE_RATE,
            audio_path=str(out_path),
        )
        return str(out_path) if Path(out_path).exists() else None
    except Exception as e:
        print(f"❌ Silero TTS не смог синтезировать: {e}")
        return None
