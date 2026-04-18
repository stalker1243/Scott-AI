from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import sys
import numpy as np
import soundfile as sf
from .voices import VoicePreset, get_voice_preset, get_jarvis_voice

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


@dataclass
class TtsConfig:
    """Конфигурация TTS движка."""
    provider: str = "edge-tts"  # "edge-tts" или "dummy"
    voice: str = "ru-RU-SvetlanaNeural"  # Голос для русского языка
    rate: str = "+0%"  # Скорость речи (-50% до +100%)
    pitch: str = "+0Hz"  # Высота тона (-50Hz до +50Hz)
    voice_preset: Optional[str] = None  # Имя пресета (jarvis, russian_male и т.д.)


class TtsEngine:
    """
    Движок синтеза речи (TTS).
    Поддерживает edge-tts (Microsoft) для качественного голоса.
    """

    def __init__(self, config: Optional[TtsConfig] = None) -> None:
        self.config = config or TtsConfig()
        self._edge_tts = None
        
        # Если указан пресет голоса, применяем его настройки
        if self.config.voice_preset:
            preset = get_voice_preset(self.config.voice_preset)
            if preset:
                self.config.voice = preset.voice
                self.config.rate = preset.rate
                self.config.pitch = preset.pitch
                print(f"✅ Используется пресет голоса: {preset.name}")
            else:
                print(f"⚠️  Пресет '{self.config.voice_preset}' не найден. Используются стандартные настройки.")

    def _init_edge_tts(self):
        """Инициализация edge-tts."""
        if self._edge_tts is not None:
            return
        
        if self.config.provider == "edge-tts":
            try:
                import edge_tts
                self._edge_tts = edge_tts
                print("✅ Edge-TTS инициализирован")
            except ImportError:
                print("⚠️  edge-tts не установлен. Используется заглушка.")
                print("💡 Установите: pip install edge-tts")
                self._edge_tts = "not_available"

    def synthesize_to_file(self, text: str, language: str, speaker: Optional[str] = None, out_path: Optional[Path] = None) -> Path:
        """
        Генерация аудио по тексту в указанный файл.
        
        Args:
            text: Текст для озвучивания
            language: Язык (ru, en и т.д.)
            speaker: Голос (опционально, используется из конфига если не указан)
            out_path: Путь для сохранения аудиофайла
            
        Returns:
            Путь к созданному файлу
        """
        if out_path is None:
            from tempfile import gettempdir
            out_path = Path(gettempdir()) / "tts_output.wav"
        
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if self.config.provider == "edge-tts":
            return self._synthesize_edge_tts(text, language, speaker or self.config.voice, out_path)
        else:
            # Заглушка для тестирования
            return self._synthesize_dummy(text, out_path)

    def _synthesize_edge_tts(self, text: str, language: str, voice: str, out_path: Path) -> Path:
        """Синтез через edge-tts."""
        self._init_edge_tts()
        
        if self._edge_tts == "not_available":
            return self._synthesize_dummy(text, out_path)
        
        import asyncio
        
        async def _generate():
            communicate = self._edge_tts.Communicate(
                text=text,
                voice=voice,
                rate=self.config.rate,
                pitch=self.config.pitch
            )
            await communicate.save(str(out_path))
            return out_path
        
        try:
            # Запускаем асинхронную функцию
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(_generate())
            loop.close()
            return result
        except Exception as e:
            print(f"⚠️  Ошибка edge-tts: {e}. Используется заглушка.")
            return self._synthesize_dummy(text, out_path)

    def _synthesize_dummy(self, text: str, out_path: Path) -> Path:
        """Заглушка - простая синусоида."""
        sr = 22050
        # Длительность зависит от длины текста (примерно)
        duration_sec = max(1.0, min(len(text) * 0.1, 10.0))
        t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False)
        
        freq = 440.0
        audio = 0.2 * np.sin(2 * np.pi * freq * t).astype(np.float32)
        
        sf.write(out_path, audio, sr)
        return out_path


def get_default_engine() -> TtsEngine:
    """Фабрика для получения движка по умолчанию."""
    return TtsEngine()
