"""Bound slow work without filling asyncio's shared executor with stuck calls."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import threading
import contextvars


class WorkBusy(RuntimeError):
    pass


class WorkTimeout(RuntimeError):
    pass


class WorkPool:
    def __init__(self, workers, name):
        self._workers = workers
        self._state_lock = threading.Lock()
        self._active = self._timeouts = self._rejected = 0
        self._slots = threading.BoundedSemaphore(workers)
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix=name)

    async def run(self, function, *args, timeout=45, cancelled=None, completion=None, **kwargs):
        def discarded():
            if completion is not None:
                completion()
        if not self._slots.acquire(blocking=False):
            with self._state_lock:
                self._rejected += 1
            discarded()
            raise WorkBusy('Все обработчики заняты. Дождитесь завершения текущих запросов.')
        with self._state_lock:
            self._active += 1
        try:
            context = contextvars.copy_context()
            future = self._executor.submit(context.run, partial(function, *args, **kwargs))
        except BaseException:
            with self._state_lock:
                self._active -= 1
            self._slots.release()
            discarded()
            raise
        def finished(_):
            # A timed-out running thread retains its slot until it REALLY ends.
            with self._state_lock:
                self._active -= 1
            self._slots.release()
            discarded()
        future.add_done_callback(finished)
        waiting = asyncio.wrap_future(future)
        def consume(result):
            if not result.cancelled():
                result.exception()  # Late failures must not become unhandled futures.
        waiting.add_done_callback(consume)
        try:
            return await asyncio.wait_for(asyncio.shield(waiting), timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError) as error:
            if cancelled is not None:
                cancelled.set()
            future.cancel()  # Only queued work can be cancelled; never fake thread cancellation.
            if isinstance(error, asyncio.CancelledError):
                raise
            with self._state_lock:
                self._timeouts += 1
            raise WorkTimeout('Время ожидания истекло. Результат операции пока не подтверждён.') from None

    def snapshot(self):
        with self._state_lock:
            return dict(limit=self._workers, in_flight=self._active, timeouts=self._timeouts, rejected=self._rejected)

    def close(self):
        self._executor.shutdown(wait=False, cancel_futures=True)


actions = WorkPool(4, 'scott-actions')
models = WorkPool(4, 'scott-models')
memory = WorkPool(2, 'scott-memory')
