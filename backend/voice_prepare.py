"""Cancellable preparation on explicit request or successful microphone activation."""
import atexit
import threading
import time
import uuid
try:
    from .scott_voice_engine import get_engine, MESSAGES
    from .scott_voice_process import VoiceProcessError
except ImportError:
    from scott_voice_engine import get_engine, MESSAGES
    from scott_voice_process import VoiceProcessError


class PrepareConflict(Exception):
    pass


class _Unavailable(ValueError):
    pass


class VoicePreparation:
    def __init__(self, provider=get_engine):
        self.provider = provider
        self._lock = threading.RLock()
        self._thread = None
        self._engine = None
        self._generation = None
        self._cancelled = False
        self._id = ''
        self._state = 'idle'
        self._message = ''
        self._for_listening = False
        self._listen_epoch = 0
        self._listen_requested = False
        self._pending_listen = None

    def snapshot(self):
        with self._lock:
            loaded = bool(self._engine and self._engine.generation==self._generation and
                self._engine.model_status().get('model_loaded'))
            state = self._state
            message = self._message
            if state=='complete' and not loaded:
                state, message = 'idle', 'Модель освобождена. Можно подготовить её снова.'
            return dict(id=self._id, state=state, message=message, model_loaded=loaded,
                idle_release_seconds=120)

    def _begin(self, for_listening):
        self._engine, self._generation = None, None
        self._id, self._cancelled = uuid.uuid4().hex, False
        self._for_listening = for_listening
        self._state, self._message = 'running', 'Загружаем модель и готовим голос…'
        return self._id

    def _current(self, ident):
        with self._lock:
            return ident==self._id and not self._cancelled

    def _validate(self, ident, engine=None, generation=None):
        engine = self.provider() if engine is None else engine
        with self._lock:
            if not self._current(ident):
                raise VoiceProcessError('cancelled')
            self._engine = engine
            self._generation = engine.generation if generation is None else generation
            generation = self._generation
        info = engine.describe()  # Native probes must not hold the status/cancel lock.
        if not self._current(ident) or engine.generation!=generation:
            raise VoiceProcessError('cancelled')
        if not info['available']:
            raise _Unavailable(info['reason'])
        return engine, generation

    def start(self):
        with self._lock:
            if self._state in ('running','cancelling'):
                raise PrepareConflict('Подготовка уже выполняется.')
            ident = self._begin(False)
        try:
            engine, generation = self._validate(ident)
        except VoiceProcessError as error:
            self._finish(ident,'cancelled','Подготовка отменена.')
            return self.snapshot()
        except _Unavailable as error:
            self._finish(ident,'failed',str(error))
            raise
        except Exception:
            self._finish(ident,'failed','Не удалось подготовить Scott Voice.')
            raise ValueError('Не удалось подготовить Scott Voice.') from None
        with self._lock:
            if not self._current(ident):
                self._finish(ident,'cancelled','Подготовка отменена.')
                return self.snapshot()
            self._thread = threading.Thread(target=self._run, args=(engine,generation,ident,False),
                name='voice-preparation', daemon=True)
            self._thread.start()
            return self.snapshot()

    def listening_requested(self):
        with self._lock:
            self._listen_epoch += 1
            self._listen_requested = True
            return self._listen_epoch

    def listening_stopped(self):
        """Invalidate delayed starts immediately; close the captured job off-loop."""
        with self._lock:
            self._listen_epoch += 1
            self._listen_requested = False
            self._pending_listen = None
            if self._for_listening and self._id:
                self._cancelled = True
                self._state = 'cancelling' if self._state in ('running','cancelling') else 'cancelled'
                self._message = 'Освобождаем модель…' if self._state=='cancelling' else 'Модель освобождена.'
                return self._id
            return None

    def listening_failed(self, epoch):
        with self._lock:
            return self.listening_stopped() if epoch==self._listen_epoch else None

    def cancel_listening(self, ident):
        if ident:
            try:
                self.cancel(ident, keep_pending=True)
            except PrepareConflict:
                pass  # A newer manual/automatic job owns the model now.

    def start_listening(self, epoch):
        with self._lock:
            if not self._listen_requested or epoch!=self._listen_epoch:
                return self.snapshot()
            if self._state=='running':
                return self.snapshot()
            if self._state=='cancelling':
                self._pending_listen = epoch
                return self.snapshot()
            ident = self._begin(True)
            self._thread = threading.Thread(target=self._automatic, args=(ident,),
                name='voice-listening-preparation', daemon=True)
            self._thread.start()
            return self.snapshot()

    def _automatic(self, ident):
        try:
            try:
                from .audio_settings import is_quiet
            except ImportError:
                from audio_settings import is_quiet
            if not self._current(ident):
                raise VoiceProcessError('cancelled')
            if is_quiet():
                self._finish(ident,'idle','')
                return
            engine = self.provider()
            with engine.listening_preparation() as generation:
                engine, generation = self._validate(ident,engine,generation)
                self._run(engine,generation,ident,True)
        except VoiceProcessError:
            self._finish(ident,'cancelled','Подготовка отменена.')
            return
        except _Unavailable as error:
            self._finish(ident,'failed',str(error))
            return
        except Exception:
            self._finish(ident,'failed','Не удалось подготовить Scott Voice.')
            return

    def _run(self, engine, generation, ident, for_listening):
        try:
            deadline = time.monotonic() + 180
            while engine.model_status().get('active'):
                if not self._current(ident) or engine.generation != generation:
                    raise VoiceProcessError('cancelled')
                if time.monotonic() >= deadline:
                    raise VoiceProcessError('timeout')
                time.sleep(.05)
            if not self._current(ident) or engine.generation!=generation:
                raise VoiceProcessError('cancelled')
            if for_listening:
                if not engine.model_status().get('model_loaded'):
                    engine.prepare(generation=generation, for_listening=True)
            else:
                engine.prepare(generation=generation)
            state, message = 'complete', 'Scott Voice готов к речи.'
        except VoiceProcessError as error:
            state = 'cancelled' if error.code in ('cancelled','closed') else 'failed'
            message = 'Подготовка отменена.' if state=='cancelled' else MESSAGES.get(error.code,'Не удалось подготовить Scott Voice.')
        except Exception:
            state, message = 'failed', 'Не удалось подготовить Scott Voice.'
        self._finish(ident,state,message)

    def _finish(self, ident, state, message):
        with self._lock:
            if ident!=self._id:
                return
            if self._cancelled:
                state, message = 'cancelled', 'Модель освобождена.'
            self._state, self._message = state, message
            pending, self._pending_listen = self._pending_listen, None
        if pending is not None:
            self.start_listening(pending)

    def cancel(self, ident, *, keep_pending=False):
        with self._lock:
            if ident!=self._id or not self._id:
                raise PrepareConflict('Эта подготовка уже не актуальна.')
            engine, generation = self._engine, self._generation
            running = self._state in ('running','cancelling')
            self._cancelled = True
            if not keep_pending:
                self._pending_listen = None
            self._state = 'cancelling' if running else 'cancelled'
            self._message = 'Освобождаем модель…' if running else 'Модель освобождена.'
        if engine:
            engine.cancel(generation=generation)
        return self.snapshot()

    def close(self):
        self.listening_stopped()
        with self._lock:
            ident, thread = self._id, self._thread
        if ident:
            self.cancel(ident)
        if thread and thread is not threading.current_thread():
            thread.join(timeout=5)


preparation = VoicePreparation()
atexit.register(preparation.close)
