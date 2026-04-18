"""
Модуль озвучки видео/мультфильмов/фильмов.

Позволяет:
1. Загрузить видео файл
2. Извлечь или распознать субтитры/речь
3. Назначить голоса персонажам
4. Сгенерировать новую озвучку
5. Смешать с видео
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
import subprocess
import sys

# Добавляем родительскую директорию в путь
_backend_path = Path(__file__).parent.parent
if str(_backend_path) not in sys.path:
    sys.path.insert(0, str(_backend_path))

from tts_core import TtsEngine, get_default_engine, list_available_voices
from asr_core import AsrEngine, get_default_asr_engine


@dataclass
class CharacterVoice:
    """Голос персонажа."""
    character_name: str
    voice_preset: str  # имя из list_available_voices()
    language: str = "ru"


@dataclass
class DialogueLine:
    """Строка диалога."""
    start_time: float  # секунды
    end_time: float
    character: str
    text: str


@dataclass
class DubbingConfig:
    """Конфигурация озвучки."""
    video_path: Path
    output_path: Path
    characters: Dict[str, CharacterVoice]  # имя персонажа -> голос
    dialogues: List[DialogueLine]
    tts_engine: Optional[TtsEngine] = None
    asr_engine: Optional[AsrEngine] = None
    # Дополнительно: простой режим "рассказчика"
    narration_text: Optional[str] = None          # если задан — можно озвучить видео одним текстом
    narration_voice_preset: Optional[str] = None  # имя пресета голоса для рассказчика
    narration_language: str = "ru"                # язык рассказчика


class VideoDubber:
    """Класс для озвучки видео."""

    def __init__(self, config: Optional[DubbingConfig] = None):
        self.config = config
        if config:
            self.tts = config.tts_engine or get_default_engine()
            self.asr = config.asr_engine or get_default_asr_engine()
        else:
            self.tts = get_default_engine()
            self.asr = get_default_asr_engine()

    def extract_subtitles(self, video_path: Path) -> List[DialogueLine]:
        """
        Извлекает субтитры из видео (если есть).
        Если субтитров нет, можно использовать ASR для распознавания.
        """
        # Пробуем извлечь субтитры через ffmpeg
        try:
            result = subprocess.run(
                ["ffmpeg", "-i", str(video_path), "-map", "0:s:0", "-c", "copy", "-"],
                capture_output=True,
                timeout=10
            )
            if result.returncode == 0:
                # Парсим субтитры (упрощённая версия)
                return self._parse_subtitles(result.stdout.decode('utf-8', errors='ignore'))
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Если субтитров нет - возвращаем пустой список
        # В будущем можно добавить ASR для распознавания речи
        return []

    def _parse_subtitles(self, subtitle_data: str) -> List[DialogueLine]:
        """Парсит субтитры (упрощённая версия)."""
        # Это упрощённая версия - в реальности нужен полноценный парсер SRT/VTT
        dialogues = []
        # TODO: Реализовать парсинг субтитров
        return dialogues

    def generate_dubbing(self, config: DubbingConfig) -> Path:
        """
        Генерирует озвучку для видео.
        
        Args:
            config: Конфигурация озвучки
            
        Returns:
            Путь к файлу с озвученным видео
        """
        print(f"🎬 Начинаю озвучку видео: {config.video_path}")
        
        # Создаём временную папку для аудио файлов
        temp_dir = config.output_path.parent / "dubbing_temp"
        temp_dir.mkdir(exist_ok=True)

        # Подготавливаем список диалогов:
        # 1) Либо используем явные диалоги (персонажи + реплики)
        # 2) Либо, если диалогов нет, но задан narration_text — озвучиваем видео как рассказчик
        dialogues: List[DialogueLine] = list(config.dialogues or [])
        characters_map: Dict[str, CharacterVoice] = dict(config.characters)

        if not dialogues and config.narration_text:
            narrator_name = "НАРРАТОР"
            preset_name = config.narration_voice_preset or "jarvis_robot_ru"
            voices = list_available_voices()
            if preset_name not in voices and voices:
                # fallback на первый доступный голос
                preset_name = next(iter(voices.keys()))

            characters_map[narrator_name] = CharacterVoice(
                character_name=narrator_name,
                voice_preset=preset_name,
                language=config.narration_language or "ru",
            )
            dialogues.append(
                DialogueLine(
                    start_time=0.0,
                    end_time=0.0,
                    character=narrator_name,
                    text=config.narration_text,
                )
            )

        # Генерируем аудио для каждой строки диалога
        audio_files = []
        for i, dialogue in enumerate(dialogues):
            character_voice = characters_map.get(dialogue.character)
            if not character_voice:
                print(f"⚠️  Нет голоса для персонажа '{dialogue.character}', пропускаю...")
                continue
            
            # Получаем настройки голоса
            voices = list_available_voices()
            voice_preset = voices.get(character_voice.voice_preset)
            if not voice_preset:
                print(f"⚠️  Голос '{character_voice.voice_preset}' не найден, пропускаю...")
                continue
            
            # Генерируем аудио
            audio_path = temp_dir / f"line_{i:04d}.wav"
            print(f"🔊 Генерирую аудио для '{dialogue.character}': {dialogue.text[:50]}...")
            
            self.tts.synthesize_to_file(
                text=dialogue.text,
                language=character_voice.language,
                speaker=voice_preset.voice,
                out_path=audio_path
            )
            
            audio_files.append((dialogue.start_time, dialogue.end_time, audio_path))
        
        # Объединяем все аудио файлы в один
        combined_audio = temp_dir / "combined_audio.wav"
        self._combine_audio_files(audio_files, combined_audio)
        
        # Смешиваем с видео
        print(f"🎞️  Смешиваю аудио с видео...")
        self._merge_audio_with_video(config.video_path, combined_audio, config.output_path)
        
        # Удаляем временные файлы
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        print(f"✅ Озвучка завершена: {config.output_path}")
        return config.output_path

    def _combine_audio_files(self, audio_files: List[Tuple[float, float, Path]], output_path: Path) -> None:
        """Объединяет аудио файлы с учётом времени."""
        # Используем ffmpeg для объединения
        # Это упрощённая версия - в реальности нужно учитывать паузы между репликами
        if not audio_files:
            return
        
        # Получаем temp_dir из первого файла
        if not audio_files:
            return
        temp_dir = audio_files[0][2].parent
        
        # Просто конкатенируем файлы (упрощённо)
        file_list = temp_dir / "file_list.txt"
        with open(file_list, 'w', encoding='utf-8') as f:
            for _, _, audio_path in audio_files:
                f.write(f"file '{audio_path.absolute()}'\n")
        
        try:
            subprocess.run(
                ["ffmpeg", "-f", "concat", "-safe", "0", "-i", str(file_list), "-c", "copy", str(output_path)],
                check=True,
                capture_output=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"⚠️  Ошибка при объединении аудио: {e}")
            # Fallback: просто копируем первый файл
            if audio_files:
                import shutil
                shutil.copy(audio_files[0][2], output_path)

    def _merge_audio_with_video(self, video_path: Path, audio_path: Path, output_path: Path) -> None:
        """Смешивает аудио с видео."""
        try:
            subprocess.run(
                [
                    "ffmpeg", "-i", str(video_path),
                    "-i", str(audio_path),
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-shortest",
                    str(output_path)
                ],
                check=True,
                capture_output=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"⚠️  Ошибка при смешивании с видео: {e}")
            # Fallback: просто копируем видео
            import shutil
            shutil.copy(video_path, output_path)

    def save_character_voices(self, characters: Dict[str, CharacterVoice], path: Path) -> None:
        """Сохраняет настройки голосов персонажей в JSON."""
        data = {
            name: {
                "voice_preset": voice.voice_preset,
                "language": voice.language
            }
            for name, voice in characters.items()
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_character_voices(self, path: Path) -> Dict[str, CharacterVoice]:
        """Загружает настройки голосов персонажей из JSON."""
        if not path.exists():
            return {}
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return {
            name: CharacterVoice(
                character_name=name,
                voice_preset=info["voice_preset"],
                language=info.get("language", "ru")
            )
            for name, info in data.items()
        }


def get_default_dubber() -> VideoDubber:
    """Фабрика для получения озвучщика по умолчанию."""
    return VideoDubber()

