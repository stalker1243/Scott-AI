"""Движок распознавания речи."""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import numpy as np


@dataclass
class AsrConfig:
    """Конфигурация ASR движка."""
    # Для цели "быстро (около 2 секунд)" в Windows/CPU обычно лучше tiny + фиксированный язык
    model_size: str = "tiny"  # tiny, base, small, medium, large
    language: Optional[str] = "ru"  # None = автоопределение, "ru", "en" и т.д.
    device: str = "cpu"  # "cpu" или "cuda"


class AsrEngine:
    """
    Движок распознавания речи на основе Whisper.
    Пока что заглушка, которая возвращает текст из файла или фиксированный ответ.
    Позже подключим реальный Whisper.
    """

    def __init__(self, config: Optional[AsrConfig] = None):
        self.config = config or AsrConfig()
        self._whisper_model = None

    @staticmethod
    def _prepare_audio(arr: np.ndarray) -> np.ndarray:
        """Лёгкая нормализация громкости для более стабильного ASR."""
        x = arr.astype(np.float32, copy=False).reshape(-1)
        if x.size == 0:
            return x
        peak = float(np.max(np.abs(x)) + 1e-9)
        # Поднимаем тихий сигнал, но не переусиливаем шум.
        gain = min(8.0, max(1.0, 0.08 / peak))
        x = np.clip(x * gain, -1.0, 1.0)
        return x

    def _load_model(self):
        """Ленивая загрузка модели Whisper."""
        if self._whisper_model is None:
            try:
                import whisper
                print(f"📥 Загрузка модели Whisper: {self.config.model_size}...")
                self._whisper_model = whisper.load_model(self.config.model_size)
                print("✅ Модель загружена!")
            except ImportError:
                print("⚠️  Whisper не установлен. Используется заглушка.")
                self._whisper_model = "dummy"

    def transcribe(self, audio_input: Path | np.ndarray) -> str:
        """
        Распознать речь из аудиофайла.
        
        Args:
            audio_input: Путь к аудиофайлу или mono float32 numpy-массив
            
        Returns:
            Распознанный текст
        """
        self._load_model()
        
        if self._whisper_model == "dummy":
            # Заглушка для тестирования без Whisper
            return "Это тестовое распознавание речи. Установите whisper для реального ASR."
        
        # Реальное распознавание через Whisper
        # Для CPU важно отключать fp16 (иначе может быть медленнее/ошибки),
        # и фиксировать язык для ускорения.
        transcribe_input: str | np.ndarray
        if isinstance(audio_input, np.ndarray):
            transcribe_input = self._prepare_audio(audio_input)
        else:
            transcribe_input = str(audio_input)

        result = self._whisper_model.transcribe(
            transcribe_input,
            language=self.config.language,
            fp16=False,
            temperature=0.0,
            beam_size=5,
            best_of=3,
            condition_on_previous_text=False,
        )
        return result["text"].strip()


def get_default_asr_engine() -> AsrEngine:
    """Фабрика для получения ASR движка по умолчанию."""
    return AsrEngine()

