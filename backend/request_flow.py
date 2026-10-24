"""Request-scoped cancellation and timings. Never records prompts or tokens."""
import contextvars
import copy
import threading
import time
import uuid
try:
    from .performance_trace import current as performance_current
except ImportError:
    from performance_trace import current as performance_current
from contextlib import contextmanager
try:
    from .timing import record
except ImportError:
    from timing import record

_current = contextvars.ContextVar('scott_request_flow', default=None)

class RequestCancelled(RuntimeError):
    pass

class Flow:
    def __init__(self, emit=None, cancelled=None, timeout=110, kind='chat', valid=None, ready=None):
        self.callback = emit
        self.ready_callback = ready
        self.cancelled = cancelled if cancelled is not None else threading.Event()
        trace = performance_current()
        trace = trace if trace is not None and trace.kind == kind else None
        self.started = trace.started if trace is not None else time.perf_counter()
        self.deadline = time.monotonic() + timeout
        self.kind = kind
        self.valid = valid
        self._first = False
        self.id = trace.id if trace is not None else uuid.uuid4().hex[:12]
        self._marks = set()
        self._mark_lock = threading.Lock()

    def mark(self, name):
        with self._mark_lock:
            if name in self._marks:
                return
            self._marks.add(name)
        record(self.kind + '.' + name, time.perf_counter() - self.started, meta={'request_id':self.id,'metric':'milestone'})

    def check(self):
        if self.cancelled.is_set() or time.monotonic() >= self.deadline or (self.valid is not None and not self.valid()):
            self.cancelled.set()
            raise RequestCancelled('Запрос остановлен.')

    def emit(self, text):
        self.check()
        if not isinstance(text, str) or not text:
            return
        if not self._first:
            self.mark('first_text')
            self._first = True
        if self.callback is not None:
            self.callback(text)

    @property
    def emitted(self):
        return self._first

    def ready_response(self, result):
        """Offer a completed reply before optional archiving; never executes it."""
        self.check()
        if self.ready_callback is None:
            return False
        self.ready_callback(result)
        self.mark('first_text')
        self._first = True
        return True

def current():
    return _current.get()

@contextmanager
def use(flow):
    token = _current.set(flow)
    try:
        yield flow
    finally:
        _current.reset(token)

def provider_snapshot(answerer):
    """Keep this request's provider/client; network I/O never owns settings lock."""
    with answerer._state_lock():
        snapshot = copy.copy(answerer)
        if isinstance(getattr(snapshot, 'client', None), dict):
            snapshot.client = dict(snapshot.client)
        return snapshot
