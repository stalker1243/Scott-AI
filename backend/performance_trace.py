"""Correlate technical durations across setup processes and voice workers. No input text."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import os
import re
import threading
import time
import uuid
try:
    from .timing import record
except ImportError:
    from timing import record

_current = ContextVar('performance_trace', default=None)


class Trace:
    def __init__(self, kind, started=None):
        inherited = os.getenv('SCOTT_TRACE_ID', '') if kind in ('setup', 'voice_setup') else ''
        self.id = inherited if re.fullmatch('[a-f0-9]{12,32}', inherited) else uuid.uuid4().hex[:12]
        self.kind = kind
        self.started = time.perf_counter() if started is None else started
        self._marks = set()
        self._lock = threading.Lock()

    def mark(self, name):
        with self._lock:
            if name in self._marks:
                return False
            self._marks.add(name)
        record(self.kind+'.'+name, max(0, time.perf_counter()-self.started),
               meta={'request_id':self.id,'metric':'milestone'})
        return True

    def duration(self, name, seconds, ok=True):
        record(self.kind+'.'+name, max(0, seconds), ok=ok,
               meta={'request_id':self.id,'metric':'duration'})


def current():
    return _current.get()


@contextmanager
def session(kind, started=None, fresh=False):
    trace = None if fresh else current()
    token = _current.set(trace or Trace(kind, started))
    try:
        yield current()
    finally:
        _current.reset(token)


def environment(values):
    """Copy rather than changing process-wide environment during concurrent work."""
    result = dict(values)
    if current() is not None:
        result['SCOTT_TRACE_ID'] = current().id
    return result


class Outcome:
    ok = True


@contextmanager
def phase(name):
    with session(name.split('.')[0]) as trace:
        started = time.perf_counter()
        outcome = Outcome()
        try:
            yield outcome
        except BaseException:
            outcome.ok = False
            raise
        finally:
            record(name, max(0, time.perf_counter()-started), ok=outcome.ok,
                   meta={'request_id':trace.id,'metric':'duration'})


def measured(name, success=None):
    def decorate(method):
        @wraps(method)
        def run(*args, **kwargs):
            with phase(name) as outcome:
                result = method(*args, **kwargs)
                if success is not None:
                    outcome.ok = bool(success(result))
                return result
        return run
    return decorate
