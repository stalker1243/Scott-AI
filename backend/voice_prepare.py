"""Manual, cancellable model preparation; no speech or automatic GPU allocation."""
import atexit
import threading
import uuid
try:
    from .scott_voice_engine import get_engine, MESSAGES
    from .scott_voice_process import VoiceProcessError
except ImportError:
    from scott_voice_engine import get_engine, MESSAGES
    from scott_voice_process import VoiceProcessError


class PrepareConflict(Exception):
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

    def start(self):
        with self._lock:
            if self._state in ('running','cancelling'):
                raise PrepareConflict('Подготовка уже выполняется.')
            engine = self.provider()
            info = engine.describe()
            if not info['available']:
                raise ValueError(info['reason'])
            if engine.model_status().get('active'):
                raise PrepareConflict('Scott Voice занят синтезом. Дождитесь окончания ответа.')
            self._engine, self._generation = engine, engine.generation
            self._id, self._cancelled = uuid.uuid4().hex, False
            self._state, self._message = 'running', 'Загружаем модель и готовим голос…'
            self._thread = threading.Thread(target=self._run, args=(engine,self._generation),
                name='voice-preparation', daemon=True)
            self._thread.start()
            return self.snapshot()

    def _run(self, engine, generation):
        try:
            engine.prepare(generation=generation)
            state, message = 'complete', 'Scott Voice готов к речи.'
        except VoiceProcessError as error:
            state = 'cancelled' if error.code in ('cancelled','closed') else 'failed'
            message = 'Подготовка отменена.' if state=='cancelled' else MESSAGES.get(error.code,'Не удалось подготовить Scott Voice.')
        except Exception:
            state, message = 'failed', 'Не удалось подготовить Scott Voice.'
        with self._lock:
            if self._cancelled:
                state, message = 'cancelled', 'Модель освобождена.'
            self._state, self._message = state, message

    def cancel(self, ident):
        with self._lock:
            if ident!=self._id or not self._id:
                raise PrepareConflict('Эта подготовка уже не актуальна.')
            engine, generation = self._engine, self._generation
            running = self._state in ('running','cancelling')
            self._cancelled = True
            self._state = 'cancelling' if running else 'cancelled'
            self._message = 'Освобождаем модель…' if running else 'Модель освобождена.'
        if engine:
            engine.cancel(generation=generation)
        return self.snapshot()

    def close(self):
        with self._lock:
            ident, thread = self._id, self._thread
        if ident:
            self.cancel(ident)
        if thread and thread is not threading.current_thread():
            thread.join(timeout=5)


preparation = VoicePreparation()
atexit.register(preparation.close)
