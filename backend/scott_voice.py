"""
Scott Voice System - Система синтеза речи
Синтез речи с голосом Scott AI
"""

import asyncio
import os
from pathlib import Path
import subprocess
import threading
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


DEFAULT_VOICE = scott_voice_engine.VOICE_ID
AVAILABLE_VOICES = {DEFAULT_VOICE: 'Scott Voice'}
VOICE_GENDERS = {DEFAULT_VOICE: 'male'}


def get_current_voice() -> str:
    """Голос, которым Scott говорит сейчас."""
    # Legacy choices never re-enable a retired provider. Reading is side-effect
    # free and no longer reads the settings file on every speech fragment.
    return DEFAULT_VOICE


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
    print(f"🎙️ Голос Scott переключён на «{voice}» ({AVAILABLE_VOICES[voice]})")
    return True


def describe_voices(gender='') -> dict:
    voices = []
    for name, label in AVAILABLE_VOICES.items():
        if gender and VOICE_GENDERS.get(name) != gender:
            continue
        info = dict(id=name, label=label, gender=VOICE_GENDERS.get(name, 'unknown'),
                    local=True, engine='qwen', available=True)
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


class ScottVoice:
    """Lightweight facade; initialization starts no model or speech thread."""
    
    def __init__(self):
        # Директория для audio файлов
        try:
            from .storage_paths import audio_cache
        except ImportError:
            from storage_paths import audio_cache
        self.audio_dir = audio_cache()
        self.audio_dir.mkdir(exist_ok=True)
        
        self._synthesis_lock = threading.RLock()
        
    
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

            streaming = voice_config.get_scott_streaming()
            куски = scott_voice_engine.speech_chunks(text, short_first=not streaming)
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
        return self._speak_parts(iter(chunks),force,cancelled,streaming=True)

    def speak_turn(self, parts, *, streaming, force=False, cancelled=None):
        """Consume the two text groups of one voice reply without draining between them."""
        try:
            from .voice_flow import _SpeechParts
        except ImportError:
            from voice_flow import _SpeechParts
        if not isinstance(parts,_SpeechParts) or type(streaming) is not bool:
            raise ValueError('Expected owned speech parts and streaming boolean')
        if cancelled is not None and not callable(cancelled):
            raise ValueError('Expected cancellation callback')
        def chunks(current):
            for text in parts.consume(current):
                yield from scott_voice_engine.speech_chunks(text,short_first=not streaming)
        return self._speak_parts(chunks,force,cancelled,streaming=streaming,source=True)

    def _speak_parts(self, chunks, force, cancelled, *, streaming, source=False):
        try:
            from .speech_player import get_player
            from .audio_settings import is_quiet
            from .speech_pipeline import QueuedSpeech
        except ImportError:
            from speech_player import get_player
            from audio_settings import is_quiet
            from speech_pipeline import QueuedSpeech
        player,engine=get_player(),scott_voice_engine.get_engine()
        generation,engine_generation=player.generation,engine.generation
        expected=(player,generation,engine,engine_generation)
        def current():
            if player.generation!=generation or engine.generation!=engine_generation \
                    or (is_quiet() and not force) or (cancelled is not None and cancelled()):
                raise scott_voice_engine.VoiceProcessError('cancelled')
        if source:
            chunks=chunks(current)
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
                        if streaming:
                            path=self._stream_phrase(chunk,force,playback,current,expected)
                        else:
                            path=self._speak_to_file_locked(chunk,scott_voice_engine.VOICE_ID,engine_generation)
                            current()
                            if path:
                                playback.submit([path],True,False)
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
            try:
                from .request_flow import current as current_flow
            except ImportError:
                from request_flow import current as current_flow
            if current_flow() is not None:
                current_flow().mark('first_audio_ready')
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
        voice = DEFAULT_VOICE if voice is None else voice
        if not isinstance(voice, str) or voice != DEFAULT_VOICE:
            return None
        generation = scott_voice_engine.get_engine().generation
        with self.__dict__.setdefault("_synthesis_lock", threading.RLock()):
            return self._speak_to_file_locked(text, voice, generation)

    def _speak_to_file_locked(self, text: str, voice: str = None, generation=None) -> str:
        """Synthesize only Scott Voice, without a cloud/system fallback."""
        if voice is not None and (not isinstance(voice, str) or voice != DEFAULT_VOICE):
            return None
        try:
            return scott_voice_engine.get_engine().synthesize(text, voice_config.get_scott_profile(), generation)
        except VoiceProcessError as failure:
            if failure.code not in ('cancelled', 'closed'):
                print(f'⚠️ Scott Voice: {failure.code}; ответ доступен в чате')
            return None
        except Exception:
            import logging
            logging.exception('Scott Voice: не удалось подготовить звук')
            return None
    
    def _cache_synthesis(self, destination: Path, synthesize):
        fd, temporary = tempfile.mkstemp(prefix=".scott-", suffix=destination.suffix, dir=self.audio_dir)
        os.close(fd)
        try:
            result = synthesize(temporary)
            if not result or not Path(temporary).exists() or Path(temporary).stat().st_size == 0:
                return None
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
_voice_lock = threading.Lock()


def get_scott_voice() -> ScottVoice:
    """Получить глобальный экземпляр ScottVoice"""
    global _scott_voice
    with _voice_lock:
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
