"""
Scott Voice System - Система синтеза речи
Синтез речи с голосом Scott AI
"""

import pyttsx3
import asyncio
import os
from pathlib import Path
import subprocess
import threading
import queue
import time

try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False

try:
    import silero_tts
    HAS_SILERO = silero_tts.is_available()
except Exception:
    silero_tts = None
    HAS_SILERO = False

# Какой движок синтеза использовать: silero (локальный, по умолчанию) или edge
# (облачный Microsoft). Silero работает офлайн и синтезирует фразу за ~15 мс
# против ~1.9 с у edge-tts, поэтому он основной; edge остаётся запасным
# вариантом и включается через TTS_ENGINE=edge в .env.
TTS_ENGINE = os.getenv("TTS_ENGINE", "silero").strip().lower()

# Edge TTS официально предлагает только два voice для ru-RU (Dmitry/Svetlana),
# но его многоязычные ("Multilingual") neural-голоса реально умеют произносить
# русский текст через автоопределение языка — проверено вручную (не падают,
# синтезируют настоящий звук, а не тишину). Добавлены как альтернативные
# варианты тембра для Scott — какой из них лучше звучит, решать на слух через
# кнопку «Прослушать» в Настройках, это не то, что можно выбрать по описанию.
# DEFAULT_VOICE можно переопределить через .env (TTS_VOICE), а конкретный
# запрос может передать свой voice (см. /text_to_speech в main.py) — так
# пользователь может переключать голос из Настроек, не трогая .env.
_ENV_VOICE = os.getenv("TTS_VOICE", "").strip()
AVAILABLE_VOICES = {
    "ru-RU-DmitryNeural": "Дмитрий (муж., ru-RU)",
    "en-US-AndrewMultilingualNeural": "Andrew (муж., многоязычный)",
    "en-US-BrianMultilingualNeural": "Brian (муж., многоязычный)",
    "en-AU-WilliamMultilingualNeural": "William (муж., многоязычный)",
    "de-DE-FlorianMultilingualNeural": "Florian (муж., многоязычный, низкий тембр)",
}

# Пол голосов — чтобы лаунчер мог показать только мужские (или только женские),
# не зашивая знание о конкретных именах голосов в интерфейс.
VOICE_GENDERS = {
    "ru-RU-DmitryNeural": "male",
    "en-US-AndrewMultilingualNeural": "male",
    "en-US-BrianMultilingualNeural": "male",
    "en-AU-WilliamMultilingualNeural": "male",
    "de-DE-FlorianMultilingualNeural": "male",
}

# Локальные голоса Silero добавляются к списку — так они появляются в выпадающем
# списке Настроек рядом с облачными, и переключение работает без правки .env.
if HAS_SILERO:
    AVAILABLE_VOICES.update(silero_tts.SILERO_VOICES)
    VOICE_GENDERS.update(silero_tts.SILERO_VOICE_GENDERS)

# Голос по умолчанию зависит от выбранного движка: для Silero это его локальный
# голос, для edge — прежний ru-RU-DmitryNeural. TTS_VOICE из .env, если задан,
# имеет приоритет над обоими.
if _ENV_VOICE:
    DEFAULT_VOICE = _ENV_VOICE
elif TTS_ENGINE == "silero" and HAS_SILERO:
    DEFAULT_VOICE = silero_tts.DEFAULT_SILERO_VOICE
else:
    DEFAULT_VOICE = "ru-RU-DmitryNeural"


def _is_silero_voice(voice: str) -> bool:
    """Голос принадлежит локальному движку Silero (а не облачному edge-tts)."""
    return HAS_SILERO and voice in silero_tts.SILERO_VOICES


# Текущий голос можно менять на лету (из Настроек лаунчера), не трогая .env и не
# перезапуская backend. DEFAULT_VOICE остаётся значением «из конфига», к которому
# всегда можно вернуться.
_current_voice = DEFAULT_VOICE


def get_current_voice() -> str:
    """Голос, которым Scott говорит сейчас."""
    return _current_voice


def set_current_voice(voice: str) -> bool:
    """
    Сменить голос до конца работы процесса. Возвращает False, если голос
    неизвестен — вызывающий код так отличит опечатку от успешной смены.
    """
    global _current_voice
    if voice not in AVAILABLE_VOICES:
        return False
    _current_voice = voice
    print(f"🎙️ Голос Scott переключён на «{voice}» ({AVAILABLE_VOICES[voice]})")
    return True
# Настройки для "роботизированного" звучания голоса (быстрее + ниже тон) —
# были заявлены в .env (TTS_RATE/TTS_PITCH), но ни разу не передавались в
# edge_tts.Communicate(), поэтому не оказывали никакого эффекта на звук.
DEFAULT_RATE = os.getenv("TTS_RATE", "+0%")
DEFAULT_PITCH = os.getenv("TTS_PITCH", "+0Hz")


class ScottVoice:
    """Система синтеза речи Scott (локальный синтез через pyttsx3)"""
    
    def __init__(self):
        # Инициализируем pyttsx3 движок
        try:
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', 150)  # скорость (слов в минуту)
            self.engine.setProperty('volume', 0.8)  # громкость (0.0 до 1.0)
            
            # Попробуем установить русский голос (если доступно)
            voices = self.engine.getProperty('voices')
            selected_voice = self._find_russian_voice(voices)
            if selected_voice:
                self.engine.setProperty('voice', selected_voice.id)
                print(f"✅ Русский голос: {selected_voice.name}")
            elif voices:
                self.engine.setProperty('voice', voices[0].id)
                print(f"✅ Голос: {voices[0].name}")
        except Exception as e:
            print(f"⚠️ Ошибка инициализации pyttsx3: {e}")
            self.engine = None
        
        # Директория для audio файлов
        self.audio_dir = Path(__file__).resolve().parent.parent / "audio_cache"
        self.audio_dir.mkdir(exist_ok=True)
        
        # Queue для изолированного выполнения TTS
        self.tts_queue = queue.Queue(maxsize=5)  # Увеличили размер
        self.tts_thread = None
        self._start_tts_worker()
        
        print("✅ Scott Voice инициализирован. Готов служить.")
    
    def _start_tts_worker(self):
        """Запускает worker thread для изолированного выполнения TTS"""
        self.tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
        self.tts_thread.start()
    
    def _tts_worker(self):
        """Worker thread для обработки TTS requests"""
        while True:
            try:
                task = self.tts_queue.get(timeout=1)
                if task is None:
                    break
                
                text, save_file, result_queue = task
                try:
                    # Создаем новый engine для каждого синтеза в worker thread
                    engine = pyttsx3.init()
                    engine.setProperty('rate', 150)
                    engine.setProperty('volume', 0.8)
                    
                    voices = engine.getProperty('voices')
                    selected_voice = self._find_russian_voice(voices)
                    if selected_voice:
                        engine.setProperty('voice', selected_voice.id)
                    elif voices:
                        engine.setProperty('voice', voices[0].id)
                    
                    # Сохраняем в файл
                    engine.save_to_file(text, save_file)
                    engine.runAndWait()
                    
                    if Path(save_file).exists() and Path(save_file).stat().st_size > 0:
                        print(f"✅ Аудио сохранено: {save_file}")
                        result_queue.put(str(save_file))
                    else:
                        raise RuntimeError(f"Файл не был создан или пуст: {save_file}")
                    
                    del engine
                except Exception as e:
                    print(f"❌ Ошибка TTS в worker: {e}")
                    result_queue.put(None)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"❌ Ошибка в TTS worker thread: {e}")
    
    def speak(self, text: str, save_file: str = None) -> str:
        """
        Говорит текст голосом Scott
        
        Args:
            text: Текст для озвучивания
            save_file: Путь для сохранения аудио (опционально)
            
        Returns:
            Путь к аудио файлу
        """
        try:
            audio_file = self.speak_to_file(text)
            if audio_file:
                self.play_audio(audio_file)
            return audio_file
        except Exception as e:
            print(f"❌ Ошибка синтеза речи: {e}")
            return None

    def _find_russian_voice(self, voices):
        """Найти первый доступный русский голос в pyttsx3"""
        if not voices:
            return None
        names = ["Irina", "Dmitry", "Anna", "Ekaterina", "Sergey", "Ivan", "Olga", "Tatyana", "Maria"]
        for voice in voices:
            if any(name.lower() in (voice.name or "").lower() for name in names):
                return voice
            if hasattr(voice, 'languages') and voice.languages:
                langs = [lang.lower() for lang in voice.languages]
                if any('ru' in lang or 'rus' in lang for lang in langs):
                    return voice
        return None

    def _save_edge_tts(self, text: str, save_file: str, voice: str = DEFAULT_VOICE) -> str:
        """Сохранить текст в файл через Edge TTS"""
        try:
            if not HAS_EDGE_TTS:
                raise RuntimeError('Edge TTS недоступен')

            async def _save_async():
                communicate = edge_tts.Communicate(text, voice=voice, rate=DEFAULT_RATE, pitch=DEFAULT_PITCH)
                await communicate.save(save_file)
                return save_file

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return asyncio.run(_save_async())
            else:
                # Запуск асинхронной операции в отдельном потоке, если event loop уже запущен
                result_queue = queue.Queue()
                thread = threading.Thread(
                    target=self._run_edge_tts_in_thread,
                    args=(text, save_file, result_queue, voice),
                    daemon=True
                )
                thread.start()
                try:
                    return result_queue.get(timeout=30)
                except queue.Empty:
                    print("⚠️ Edge TTS timeout (30s)")
                    return None

        except Exception as e:
            print(f"❌ Ошибка Edge TTS: {e}")
            return None

    def _run_edge_tts_in_thread(self, text: str, save_file: str, result_queue: queue.Queue, voice: str = DEFAULT_VOICE):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            communicate = edge_tts.Communicate(text, voice=voice, rate=DEFAULT_RATE, pitch=DEFAULT_PITCH)
            loop.run_until_complete(communicate.save(save_file))
            result_queue.put(save_file)
        except Exception as e:
            print(f"❌ Ошибка Edge TTS в потоке: {e}")
            result_queue.put(None)
        finally:
            try:
                loop.close()
            except Exception:
                pass

    def _speak_sync(self, text: str, save_file: str) -> str:
        """
        Синхронный синтез речи через worker thread (с timeout)
        
        Args:
            text: Текст для озвучивания
            save_file: Путь для сохранения
            
        Returns:
            Путь к сохраненному файлу
        """
        try:
            result_queue = queue.Queue()
            task = (text, save_file, result_queue)
            
            # Отправляем задачу в queue (с timeout чтобы избежать зависания)
            try:
                self.tts_queue.put(task, timeout=1)
            except queue.Full:
                print(f"⚠️  TTS queue полная, используем кэш")
                return None
            
            # Ждем результат с timeout
            try:
                result = result_queue.get(timeout=15)
                return result
            except queue.Empty:
                print(f"⚠️  TTS timeout (15s)")
                return None
                
        except Exception as e:
            print(f"❌ Ошибка в _speak_sync: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def speak_to_file(self, text: str, voice: str = None) -> str:
        """
        Синхронный метод для озвучивания текста и сохранения в файл

        Args:
            text: Текст для озвучивания
            voice: Имя голоса Edge TTS (например, 'ru-RU-SvetlanaNeural');
                   по умолчанию — DEFAULT_VOICE (см. .env TTS_VOICE)

        Returns:
            Путь к аудио файлу
        """
        voice = voice or get_current_voice()
        try:
            import hashlib
            use_silero = _is_silero_voice(voice)

            try:
                from .speech_text import prepare_for_speech, strip_decoration, has_speakable_content
            except ImportError:
                from speech_text import prepare_for_speech, strip_decoration, has_speakable_content

            # Silero говорит только по-русски: числа и латиницу он молча
            # выбрасывает, и «Запущено 285 процессов» звучит как «запущено
            # процессов». Поэтому текст для него разворачивается словами, а для
            # облачного edge-tts достаточно снять эмодзи — с числами и
            # английским он справляется сам.
            spoken_text = prepare_for_speech(text) if use_silero else strip_decoration(text).strip()

            if use_silero and not has_speakable_content(spoken_text):
                # Ни одной русской буквы — Silero на таком тексте бросает
                # ValueError, и это выглядело как сбой движка: синтез молча
                # уходил в облако. Честнее сразу отдать это edge-tts.
                print(f"ℹ️ Нечего произносить по-русски в «{text[:40]}» — беру Edge TTS")
                use_silero = False
                voice = "ru-RU-DmitryNeural"
                spoken_text = strip_decoration(text).strip()
            # Silero отдаёт WAV, edge-tts — MP3. Расширение входит в имя файла,
            # иначе кэш вернул бы WAV под видом mp3 и плеер бы на нём споткнулся.
            extension = "wav" if use_silero else "mp3"
            # Голос/скорость/тон — часть ключа кэша: иначе при смене голоса в
            # Настройках вернулся бы старый файл, озвученный прежним голосом.
            # Ключ считается по ПОДГОТОВЛЕННОМУ тексту: разные исходники, звучащие
            # одинаково, разумно делить один файл. Прежние файлы кэша при
            # изменении подготовки просто перестают совпадать и создаются заново.
            hash_text = hashlib.md5(f"{voice}:{DEFAULT_RATE}:{DEFAULT_PITCH}:{spoken_text}".encode()).hexdigest()[:8]
            save_file = self.audio_dir / f"scott_{hash_text}.{extension}"
            save_file = save_file.resolve()

            if Path(save_file).exists() and Path(save_file).stat().st_size > 0:
                print(f"📦 Используется кэшированный аудио: {save_file}")
                return str(save_file)

            if use_silero:
                print(f"🎙️ Локальный синтез Silero (голос: {voice})")
                silero_file = silero_tts.synthesize(spoken_text, str(save_file), voice)
                if silero_file:
                    return silero_file
                # Локальный движок не справился — не оставляем Scott немым,
                # пробуем облачный edge-tts прежним голосом.
                print("⚠️ Silero не дал результата, пробую Edge TTS")
                voice = "ru-RU-DmitryNeural"
                save_file = self.audio_dir / f"scott_{hash_text}.mp3"
                save_file = save_file.resolve()

            if HAS_EDGE_TTS:
                print(f"🎙️ Используем Edge TTS для синтеза (голос: {voice})")
                edge_file = self._save_edge_tts(spoken_text, str(save_file), voice)
                return edge_file

            if not self.engine:
                raise RuntimeError("Движок pyttsx3 не инициализирован")

            result = self._speak_sync(text, str(save_file))
            return result

        except Exception as e:
            print(f"❌ Ошибка в speak_to_file: {e}")
            import traceback
            traceback.print_exc()
            return None
    
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
_scott_voice = None


def get_scott_voice() -> ScottVoice:
    """Получить глобальный экземпляр ScottVoice"""
    global _scott_voice
    if _scott_voice is None:
        _scott_voice = ScottVoice()
    return _scott_voice


# Асинхронный вспомогательный класс
class ScottVoiceAsync:
    """Асинхронная обёртка для ScottVoice"""
    
    def __init__(self):
        self.voice = get_scott_voice()
    
    async def speak_and_play(self, text: str):
        """Говорить и воспроизвести"""
        audio_file = await asyncio.to_thread(self.voice.speak, text)
        if audio_file:
            self.voice.play_audio(audio_file)


if __name__ == "__main__":
    # Тест
    import asyncio
    
    scott = ScottVoice()
    
    async def test():
        await asyncio.to_thread(scott.speak, "Привет, это Scott Voice System")
    
    asyncio.run(test())
