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
import tempfile
try:
    from . import voice_config
    from .speech_buffer import SpeechBuffer, BUFFER_MODES, join_wavs
except ImportError:
    import voice_config
    from speech_buffer import SpeechBuffer, BUFFER_MODES, join_wavs
try:
    from . import scott_voice_engine
    from .scott_voice_process import VoiceProcessError
except ImportError:
    import scott_voice_engine
    from scott_voice_process import VoiceProcessError

EDGE_TIMEOUT_SECONDS = 25

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

try:
    from timing import stage as _замер
except ImportError:  # pragma: no cover — запуск из корня репозитория
    try:
        from .timing import stage as _замер
    except ImportError:
        from contextlib import contextmanager

        @contextmanager
        def _замер(name: str):
            """Заглушка: без модуля замеров синтез должен работать как обычно."""
            yield


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
    "ru-RU-SvetlanaNeural": "Светлана (жен., ru-RU)",
    "en-US-AndrewMultilingualNeural": "Andrew (муж., многоязычный)",
    "en-US-BrianMultilingualNeural": "Brian (муж., многоязычный)",
    "en-AU-WilliamMultilingualNeural": "William (муж., многоязычный)",
    "de-DE-FlorianMultilingualNeural": "Florian (муж., многоязычный, низкий тембр)",
}

# Пол голосов — чтобы лаунчер мог показать только мужские (или только женские),
# не зашивая знание о конкретных именах голосов в интерфейс.
VOICE_GENDERS = {
    "ru-RU-DmitryNeural": "male",
    "ru-RU-SvetlanaNeural": "female",
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
AVAILABLE_VOICES[scott_voice_engine.VOICE_ID] = 'Scott Voice (муж., экспериментальный)'
VOICE_GENDERS[scott_voice_engine.VOICE_ID] = 'male'

# Голос по умолчанию зависит от выбранного движка: для Silero это его локальный
# голос, для edge — прежний ru-RU-DmitryNeural. TTS_VOICE из .env, если задан,
# имеет приоритет над обоими.
if _ENV_VOICE in AVAILABLE_VOICES:
    DEFAULT_VOICE = _ENV_VOICE
elif TTS_ENGINE == "silero" and HAS_SILERO:
    DEFAULT_VOICE = silero_tts.DEFAULT_SILERO_VOICE
else:
    DEFAULT_VOICE = "ru-RU-DmitryNeural"


def _is_silero_voice(voice: str) -> bool:
    """Голос принадлежит локальному движку Silero (а не облачному edge-tts)."""
    return HAS_SILERO and voice in silero_tts.SILERO_VOICES


# An explicit saved choice overrides the default from the environment.


def get_current_voice() -> str:
    """Голос, которым Scott говорит сейчас."""
    return voice_config.get_voice(DEFAULT_VOICE, AVAILABLE_VOICES)


def set_current_voice(voice: str, profile=None, streaming=None, acceleration=None, buffer_mode=None) -> bool:
    """
    Сменить голос и сохранить выбор. Возвращает False, если голос
    неизвестен — вызывающий код так отличит опечатку от успешной смены.
    """
    if not isinstance(voice, str) or voice not in AVAILABLE_VOICES:
        return False
    if voice == scott_voice_engine.VOICE_ID and not scott_voice_engine.get_engine().describe()['available']:
        return False
    voice_config.save_voice(voice, profile, streaming, acceleration, buffer_mode)
    if voice==scott_voice_engine.VOICE_ID:
        scott_voice_engine.get_engine().set_acceleration(voice_config.get_scott_acceleration())
    else:
        scott_voice_engine.cancel()
    print(f"🎙️ Голос Scott переключён на «{voice}» ({AVAILABLE_VOICES[voice]})")
    return True


def describe_voices(gender='') -> dict:
    voices = []
    for name, label in AVAILABLE_VOICES.items():
        if gender and VOICE_GENDERS.get(name) != gender:
            continue
        local = _is_silero_voice(name)
        info = dict(id=name, label=label, gender=VOICE_GENDERS.get(name, 'unknown'),
                    local=local, engine='silero' if local else 'edge', available=True)
        if name == scott_voice_engine.VOICE_ID:
            info.update(scott_voice_engine.get_engine().describe())
        voices.append(info)
    return dict(voices=voices, default=DEFAULT_VOICE, current=get_current_voice(),
        scott_profile=voice_config.get_scott_profile(),
        scott_streaming=voice_config.get_scott_streaming(),
        scott_acceleration=voice_config.get_scott_acceleration(),
        scott_buffer=voice_config.get_scott_buffer(),
        scott_buffers=[dict(id=name, title=choice[0]) for name, choice in BUFFER_MODES.items()],
        scott_profiles=[dict(id=name, title=title) for name, title in scott_voice_engine.PROFILES.items()])
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
    
    def speak(self, text: str, save_file: str = None, force: bool = False) -> str:
        """
        Говорит текст голосом Scott

        Args:
            text: Текст для озвучивания
            save_file: Путь для сохранения аудио (опционально)
            force: говорить даже в тихом режиме — только для прослушивания
                голоса в настройках

        Returns:
            Путь к аудио файлу
        """
        try:
            # В тихом режиме не синтезируем вовсе. Проигрыватель отбросил бы
            # готовый файл и сам, но синтез занимает секунды работы видеокарты
            # ради звука, который никто не услышит.
            try:
                from audio_settings import is_quiet
            except ImportError:
                from .audio_settings import is_quiet
            if is_quiet() and not force:
                return None

            try:
                from speech_player import get_player
            except ImportError:
                from .speech_player import get_player
            player = get_player()
            generation = player.generation

            try:
                from .speech_text import split_for_speech
            except ImportError:
                from speech_text import split_for_speech

            if get_current_voice() == scott_voice_engine.VOICE_ID:
                streaming=voice_config.get_scott_streaming()
                куски = scott_voice_engine.speech_chunks(text,short_first=not streaming)
            else:
                streaming=False
                куски = split_for_speech(text)
            if streaming:
                return self.speak_stream_parts(куски,force=force,
                    cancelled=lambda:player.generation!=generation)

            # Короткий ответ синтезируется целиком: делить «Готово» нечего, и
            # оно почти всегда уже лежит в кэше озвученных реплик.
            if len(куски) < 2:
                audio_file = self.speak_to_file(text)
                if player.generation != generation:
                    return None
                if audio_file:
                    if self.play_audio(audio_file, force=force) is False:
                        return None
                return audio_file

            # Длинный ответ — по частям. Прежде он синтезировался целиком, и
            # только потом начинал звучать: до 2,4 секунды тишины после
            # команды, в которые человек не знает, услышали его или нет.
            # Теперь первое предложение уходит в звук сразу, а остальное
            # доготавливается, пока оно играет.
            первый = None

            for номер, кусок in enumerate(куски):
                if player.generation != generation:
                    return None
                # Первый кусок замеряется отдельно: именно он и есть задержка,
                # которую слышит человек — сколько тишины проходит между
                # командой и первым словом ответа. Общий замер озвучки для
                # этого не годится: он включает время, пока Scott говорит, и
                # растёт вместе с длиной ответа.
                if номер == 0:
                    with _замер("02.синтез_речи.до_первого_слова"):
                        файл = self.speak_to_file(кусок)
                else:
                    файл = self.speak_to_file(кусок)

                if not файл or player.generation != generation:
                    return None

                if первый is None:
                    первый = файл

                # Ждём только последний: очередь проигрывателя и без того
                # последовательна, а ожидание каждого куска свело бы всю затею
                # на нет — синтез следующего начинался бы после того, как
                # предыдущий отзвучал.
                последний = номер == len(куски) - 1
                if self.play_audio(файл, force=force, wait=последний) is False:
                    return None

            return первый
        except Exception as e:
            print(f"❌ Ошибка синтеза речи: {e}")
            return None

    def _придать_характер(self, path: str, character: str) -> None:
        """
        Обработать синтезированный файл по выбранному характеру.

        Голосов у локальной модели пять, и все обычные человеческие: сделать
        звучание узнаваемым сменой голоса нельзя, а обработкой — можно. Стоит
        это тридцать миллисекунд на фразу, и только один раз: файл ложится в
        кэш уже обработанным.

        Беда здесь не повод остаться без ответа — необработанный голос всё
        равно голос.
        """
        if character == "natural":
            return

        try:
            try:
                from . import voice_character
            except ImportError:
                import voice_character

            voice_character.apply_to_file(path, character)
        except Exception as e:
            print(f"⚠️ Характер голоса не применён: {e}")

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
                await asyncio.wait_for(communicate.save(save_file), timeout=EDGE_TIMEOUT_SECONDS)
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
                    return result_queue.get(timeout=EDGE_TIMEOUT_SECONDS + 2)
                except queue.Empty:
                    print("⚠️ Edge TTS: превышено время ожидания")
                    return None

        except Exception as e:
            print(f"❌ Ошибка Edge TTS: {e}")
            return None

    def _run_edge_tts_in_thread(self, text: str, save_file: str, result_queue: queue.Queue, voice: str = DEFAULT_VOICE):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            communicate = edge_tts.Communicate(text, voice=voice, rate=DEFAULT_RATE, pitch=DEFAULT_PITCH)
            loop.run_until_complete(asyncio.wait_for(communicate.save(save_file), timeout=EDGE_TIMEOUT_SECONDS))
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
    
    def speak_stream(self, text, force=False):
        return self._stream_phrase(text,force=force)

    def speak_stream_parts(self, chunks, force=False, cancelled=None):
        """Prepare at most one next phrase while the current audio is playing."""
        try:
            from .speech_player import get_player
            from .audio_settings import is_quiet
            from .speech_pipeline import QueuedSpeech
        except ImportError:
            from speech_player import get_player
            from audio_settings import is_quiet
            from speech_pipeline import QueuedSpeech
        if cancelled is not None and not callable(cancelled):
            raise ValueError('Expected cancellation callback')
        if not isinstance(chunks,(list,tuple)) or any(not isinstance(v,str) or not v.strip() for v in chunks):
            raise ValueError('Expected speech phrases')
        if not chunks:
            return None
        player,engine=get_player(),scott_voice_engine.get_engine()
        generation,engine_generation=player.generation,engine.generation
        expected=(player,generation,engine,engine_generation)
        def current():
            if player.generation!=generation or engine.generation!=engine_generation \
                    or (is_quiet() and not force) or (cancelled is not None and cancelled()):
                raise scott_voice_engine.VoiceProcessError('cancelled')
        pending=[]
        first=None
        success=False
        try:
            with self.__dict__.setdefault('_synthesis_lock',threading.RLock()):
                for chunk in chunks:
                    current()
                    # One current phrase plus one next phrase; cached replies
                    # must not run arbitrarily far ahead of the sound device.
                    if len(pending)==2:
                        if not pending.pop(0).wait(current):
                            return None
                    playback=QueuedSpeech(player,generation,force)
                    try:
                        path=self._stream_phrase(chunk,force,playback,current,expected)
                    finally:
                        playback.seal()
                    if not path:
                        return None
                    first=first or path
                    pending.append(playback)
                for playback in pending:
                    if not playback.wait(current):
                        return None
                current()
                success=True
                return first
        except scott_voice_engine.VoiceProcessError:
            return None
        finally:
            if not success:
                player.stop(generation=generation)

    def _stream_phrase(self, text, force=False, playback=None, current=None, expected=None):
        """Queue verified blocks, stop failed partial output, and never replay it."""
        try:
            from .speech_player import get_player
            from .audio_settings import is_quiet
        except ImportError:
            from speech_player import get_player
            from audio_settings import is_quiet
        if expected is None:
            player=get_player()
            engine=scott_voice_engine.get_engine()
            generation,engine_generation=player.generation,engine.generation
        else:
            player,generation,engine,engine_generation=expected
        started=False
        stream_token=object()
        buffer=SpeechBuffer(voice_config.get_scott_buffer())
        directory=None
        def abort():
            buffer.discard()
            if started:
                player.stop(generation=generation)
        def check_current():
            if current is not None:
                current()
            if player.generation!=generation or engine.generation!=engine_generation or (is_quiet() and not force):
                raise scott_voice_engine.VoiceProcessError('cancelled')
        def output(audio,last):
            nonlocal started,directory
            check_current()
            ready=buffer.push(audio,last)
            if not ready:
                return
            path=ready[0].path
            if len(ready)>1 and playback is None:
                directory=tempfile.TemporaryDirectory(prefix='.scott-playback-',dir=Path(path).parent,ignore_cleanup_errors=True)
                path=join_wavs([block.path for block in ready],Path(directory.name)/'initial.wav')
            check_current()
            stream_play=getattr(player,'play_stream',None)
            use_stream=callable(stream_play) and (started or not last)
            started=True
            try:
                if playback is not None:
                    played=playback.submit([block.path for block in ready],last,use_stream)
                elif use_stream:
                    played=stream_play(path,stream_token,last=last,force=force,generation=generation)
                else:
                    played=(player.play_and_wait if last else player.play)(path,force=force,generation=generation)
            except Exception:
                abort()
                raise
            if played is False:
                abort()
                raise scott_voice_engine.VoiceProcessError('cancelled')
        try:
            with self.__dict__.setdefault('_synthesis_lock',threading.RLock()):
                try:
                    check_current()
                    return engine.stream(text,voice_config.get_scott_profile(),output,abort,engine_generation)
                except scott_voice_engine.VoiceProcessError as error:
                    if started or error.code in ('cancelled','closed') or engine.generation!=engine_generation:
                        abort()
                        return None
                    path=self._speak_to_file_locked(text,scott_voice_engine.VOICE_ID,engine_generation)
                    if path and player.generation==generation:
                        check_current()
                        if playback is not None:
                            playback.submit([path],True,False)
                            return path
                        if player.play_and_wait(path,force=force,generation=generation) is not False:
                            return path
                    return None
        finally:
            buffer.discard()
            if directory is not None:
                directory.cleanup()

    def speak_to_file(self, text: str, voice: str = None) -> str:
        # Concurrent previews, reminders and voice replies must not share a
        # partially written file or call the same synthesizer simultaneously.
        voice = voice or get_current_voice()
        generation = scott_voice_engine.get_engine().generation if voice == scott_voice_engine.VOICE_ID else None
        with self.__dict__.setdefault("_synthesis_lock", threading.RLock()):
            return self._speak_to_file_locked(text, voice, generation)

    def _speak_to_file_locked(self, text: str, voice: str = None, generation=None) -> str:
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
            if voice == scott_voice_engine.VOICE_ID:
                try:
                    return scott_voice_engine.get_engine().synthesize(text, voice_config.get_scott_profile(), generation)
                except VoiceProcessError as failure:
                    if failure.code in ('cancelled', 'closed'):
                        return None
                    if generation is not None and generation != scott_voice_engine.get_engine().generation:
                        return None
                    print(f"⚠️ Scott Voice: {failure.code}; используется резервный голос")
                # A failed/uninstalled optional engine never rewrites the user's choice.
                default = silero_tts.DEFAULT_SILERO_VOICE if HAS_SILERO else 'ru-RU-DmitryNeural'
                voice = voice_config.get_fallback_voice(default, AVAILABLE_VOICES)
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
            # Характер звучания входит в ключ обязательно: файлы кэша лежат
            # обработанными, и без этого после смены характера вернулся бы
            # старый файл, обработанный по-прежнему, — человек решил бы, что
            # настройка не работает.
            try:
                from .audio_settings import get_character
            except ImportError:
                from audio_settings import get_character
            character = get_character()

            hash_text = hashlib.sha256(
                f"{voice}:{DEFAULT_RATE}:{DEFAULT_PITCH}:{character}:{spoken_text}".encode()
            ).hexdigest()[:24]
            save_file = self.audio_dir / f"scott_{hash_text}.{extension}"
            save_file = save_file.resolve()

            if Path(save_file).exists() and Path(save_file).stat().st_size > 0:
                print(f"📦 Используется кэшированный аудио: {save_file}")
                return str(save_file)

            if use_silero:
                print(f"🎙️ Локальный синтез Silero (голос: {voice})")
                silero_file = self._cache_synthesis(save_file,
                    lambda path: silero_tts.synthesize(spoken_text, path, voice), character)
                if silero_file:
                    return silero_file
                # Локальный движок не справился — не оставляем Scott немым,
                # пробуем облачный edge-tts прежним голосом.
                print("⚠️ Silero не дал результата, пробую Edge TTS")
                voice = "ru-RU-DmitryNeural"
                spoken_text = strip_decoration(text).strip()
                # Include the actual fallback voice in its own cache key.
                fallback_hash = hashlib.sha256(f"edge:{voice}:{DEFAULT_RATE}:{DEFAULT_PITCH}:{spoken_text}".encode()).hexdigest()[:24]
                save_file = self.audio_dir / f"scott_{fallback_hash}.mp3"
                save_file = save_file.resolve()
                if save_file.exists() and save_file.stat().st_size > 0:
                    return str(save_file)

            if HAS_EDGE_TTS:
                print(f"🎙️ Используем Edge TTS для синтеза (голос: {voice})")
                edge_file = self._cache_synthesis(save_file,
                    lambda path: self._save_edge_tts(spoken_text, path, voice))
                if edge_file:
                    return edge_file
                print("⚠️ Edge TTS не дал результата, пробую системный голос")

            if not self.engine:
                raise RuntimeError("Движок pyttsx3 не инициализирован")

            # pyttsx3 produces WAV. Saving it as .mp3 sent the player down the
            # MP3 decoder path, so the local fallback looked like silence.
            system_hash = hashlib.sha256(f"pyttsx3:{text}".encode()).hexdigest()[:24]
            save_file = self.audio_dir / f"scott_{system_hash}.wav"
            if save_file.exists() and save_file.stat().st_size > 0:
                return str(save_file)
            result = self._cache_synthesis(save_file, lambda path: self._speak_sync(text, path))
            return result

        except Exception as e:
            print(f"❌ Ошибка в speak_to_file: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _cache_synthesis(self, destination: Path, synthesize, character=None):
        fd, temporary = tempfile.mkstemp(prefix=".scott-", suffix=destination.suffix, dir=self.audio_dir)
        os.close(fd)
        try:
            result = synthesize(temporary)
            if not result or not Path(temporary).exists() or Path(temporary).stat().st_size == 0:
                return None
            if character is not None:
                self._придать_характер(temporary, character)
            os.replace(temporary, destination)
            return str(destination)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def play_audio(self, audio_file: str, force: bool = False, wait: bool = True):
        """
        Воспроизвести аудио файл

        Args:
            audio_file: Путь к аудио файлу
            force: играть даже в тихом режиме. Нужно единственному месту —
                кнопке «Прослушать» в настройках голоса: там человек просит
                звук прямо сейчас и ждёт его.
            wait: дождаться, пока фраза отзвучит. Ждать нужно на последнем
                куске ответа: слушатель держит микрофон приостановленным всё
                время речи, иначе Scott услышит сам себя и примет свой ответ
                за команду. На промежуточных кусках ждать нельзя — синтез
                следующего начинался бы только после того, как отзвучал
                предыдущий, и говорить по частям не имело бы смысла.
        """
        try:
            try:
                from speech_player import get_player, PLAYBACK_AVAILABLE
            except ImportError:
                from .speech_player import get_player, PLAYBACK_AVAILABLE
            player = get_player()
            generation = player.generation
            if audio_file.endswith('.mp3'):
                # Конвертировать MP3 -> WAV для воспроизведения
                wav_file = audio_file.replace('.mp3', '.wav')
                with self.__dict__.setdefault('_conversion_lock', threading.Lock()):
                    if not os.path.exists(wav_file) or os.path.getsize(wav_file) == 0:
                        from pydub import AudioSegment
                        sound = AudioSegment.from_mp3(audio_file)
                        def convert(path):
                            sound.export(path, format='wav')
                            return path
                        if not self._cache_synthesis(Path(wav_file), convert):
                            raise RuntimeError('Не удалось преобразовать звук в WAV')
                audio_file = wav_file
            
            # Через общую очередь, а не напрямую: два ответа, попавшие сюда
            # одновременно, раньше звучали разом — на слух получался набор
            # слов, выпаленных сразу все. Очередь пропускает по одной фразе.
            if PLAYBACK_AVAILABLE:
                if wait:
                    return player.play_and_wait(audio_file, force=force, generation=generation)
                else:
                    # Не ждём: нужно вернуться к синтезу следующего куска, пока
                    # этот играет. Очередь проигрывателя сама пропустит фразы
                    # по одной.
                    return player.play(audio_file, force=force, generation=generation)

            # Тихий режим соблюдается и на запасном пути: иначе на машине
            # без sounddevice просьба помолчать просто не работала бы, а
            # понять почему человек бы не смог.
            try:
                from audio_settings import is_quiet
            except ImportError:
                from .audio_settings import is_quiet
            if is_quiet() and not force:
                return False

            # Запасной путь для машин без sounddevice: как раньше, через
            # PowerShell. Наложение здесь возможно, но лучше так, чем немой
            # ассистент.
            escaped = str(Path(audio_file).resolve()).replace("'", "''")
            ps_command = f"$ErrorActionPreference='Stop'; (New-Object Media.SoundPlayer '{escaped}').PlaySync()"
            subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_command],
                           check=True, timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            return True
            
        except Exception as e:
            print(f"❌ Ошибка воспроизведения: {e}")
            raise


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
        return audio_file


if __name__ == "__main__":
    # Тест
    import asyncio
    
    scott = ScottVoice()
    
    async def test():
        await asyncio.to_thread(scott.speak, "Привет, это Scott Voice System")
    
    asyncio.run(test())
