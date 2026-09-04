"""
Джарвис-голос (JARVIS Voice System)
Синтез речи с голосом похожим на Джарвиса из Железного Человека
Поддерживает несколько вариантов голосов
"""

import edge_tts
import asyncio
import os
from pathlib import Path
import subprocess


class JarvisVoice:
    """Система синтеза речи с голосом Джарвиса - поддерживает несколько голосов"""
    
    # Словарь с вариантами голосов
    VOICES = {
        'dmitry': {
            'voice': 'ru-RU-DmitryNeural',
            'rate': '+0%',
            'pitch': '-5Hz',
            'volume': '+100%',
            'name': 'Дмитрий (Русский)'
        },
        'ryan': {
            'voice': 'en-GB-RyanNeural',
            'rate': '+15%',
            'pitch': '-10Hz',
            'volume': '+100%',
            'name': 'Ryan (Британский JARVIS)'
        },
        'neural': {
            'voice': 'en-US-GuyNeural',
            'rate': '+10%',
            'pitch': '-8Hz',
            'volume': '+100%',
            'name': 'Neural (Нейросетевой)'
        },
        'amira': {
            'voice': 'en-US-AriaNeural',
            'rate': '+5%',
            'pitch': '+0Hz',
            'volume': '+100%',
            'name': 'Amira (Женский)'
        }
    }
    
    def __init__(self, voice_type: str = 'dmitry'):
        # Установить голос
        self.voice_type = voice_type if voice_type in self.VOICES else 'dmitry'
        self.update_voice_settings()
        
        # Директория для audio файлов
        self.audio_dir = Path("audio_cache")
        self.audio_dir.mkdir(exist_ok=True)
        
        print(f"✅ Джарвис инициализирован. Голос: {self.VOICES[self.voice_type]['name']}")
    
    def set_voice(self, voice_type: str) -> bool:
        """
        Установить другой голос
        
        Args:
            voice_type: Тип голоса (dmitry, ryan, neural, amira)
            
        Returns:
            True если успешно, False если голос не найден
        """
        if voice_type not in self.VOICES:
            print(f"❌ Голос '{voice_type}' не найден. Доступные: {list(self.VOICES.keys())}")
            return False
        
        self.voice_type = voice_type
        self.update_voice_settings()
        print(f"✅ Голос изменён на: {self.VOICES[self.voice_type]['name']}")
        return True
    
    def update_voice_settings(self):
        """Обновить параметры голоса на основе текущего типа"""
        settings = self.VOICES[self.voice_type]
        self.voice = settings['voice']
        self.rate = settings['rate']
        self.pitch = settings['pitch']
        self.volume = settings['volume']
    
    async def speak(self, text: str, save_file: str = None) -> str:
        """
        Говорит текст выбранным голосом
        
        Args:
            text: Текст для озвучивания
            save_file: Путь для сохранения аудио (опционально)
            
        Returns:
            Путь к аудио файлу
        """
        try:
            # Определить путь
            if save_file is None:
                import hashlib
                hash_text = hashlib.md5(text.encode()).hexdigest()[:8]
                save_file = self.audio_dir / f"jarvis_{self.voice_type}_{hash_text}.mp3"
            
            # Проверить кэш
            if Path(save_file).exists():
                print(f"📦 Используется кэшированный аудио: {save_file}")
                return str(save_file)
            
            # Синтезировать
            voice_name = self.VOICES[self.voice_type]['name']
            print(f"🎙️ {voice_name} говорит: {text[:50]}...")
            
            communicate = edge_tts.Communicate(
                text,
                self.voice,
                rate=self.rate,
                pitch=self.pitch,
                volume=self.volume
            )
            
            await communicate.save(str(save_file))
            print(f"✅ Аудио сохранено: {save_file}")
            
            return str(save_file)
            
        except Exception as e:
            print(f"❌ Ошибка синтеза речи: {e}")
            return None
    
    def speak_to_file(self, text: str) -> str:
        """
        Синхронный метод для озвучивания текста и сохранения в файл
        
        Args:
            text: Текст для озвучивания
            
        Returns:
            Путь к аудио файлу
        """
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.speak(text))
            return result
        except Exception as e:
            print(f"❌ Ошибка в speak_to_file: {e}")
            return None
        finally:
            loop.close()
    
    def play_audio(self, audio_file: str):
        """
        Воспроизвести аудио файл
        
        Args:
            audio_file: Путь к аудио файлу
        """
        try:
            if audio_file.endswith('.mp3'):
                # Конвертировать MP3 -> WAV для воспроизведения
                wav_file = audio_file.replace('.mp3', '.wav')
                if not os.path.exists(wav_file):
                    from pydub import AudioSegment
                    sound = AudioSegment.from_mp3(audio_file)
                    sound.export(wav_file, format="wav")
                audio_file = wav_file
            
            # Воспроизвести через PowerShell
            ps_command = f'(New-Object Media.SoundPlayer "{audio_file}").PlaySync()'
            subprocess.run(["powershell", "-c", ps_command], check=False)
            
        except Exception as e:
            print(f"❌ Ошибка воспроизведения: {e}")


# Глобальный экземпляр
_jarvis_voice = None


def get_jarvis_voice() -> JarvisVoice:
    """Получить глобальный экземпляр JarvisVoice"""
    global _jarvis_voice
    if _jarvis_voice is None:
        _jarvis_voice = JarvisVoice()
    return _jarvis_voice


# Асинхронный вспомогательный класс
class JarvisVoiceAsync:
    """Асинхронная обёртка для JarvisVoice"""
    
    def __init__(self):
        self.voice = get_jarvis_voice()
    
    async def speak_and_play(self, text: str):
        """Говорить и воспроизвести"""
        audio_file = await self.voice.speak(text)
        if audio_file:
            self.voice.play_audio(audio_file)


if __name__ == "__main__":
    # Тест
    import asyncio
    
    jarvis = JarvisVoice()
    
    async def test():
        await jarvis.speak("Good day. I am JARVIS. At your service.")
    
    asyncio.run(test())
