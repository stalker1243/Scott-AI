"""Start one complete sentence while the model produces the rest of its reply."""
import asyncio
import re
try:
    from . import request_flow
except ImportError:
    import request_flow

class _SpeechParts:
    """At most the opening sentence and its continuation, owned by one turn."""
    def __init__(self):
        from collections import deque
        import threading
        self._condition = threading.Condition()
        self._pending = deque()
        self._offered = []
        self._closed = False
        self._cancelled = False
        self._consumer = False
        self._observer = None

    def offer(self, text):
        if not isinstance(text,str) or not text.strip() or len(text)>65536:
            raise ValueError('Invalid speech part')
        with self._condition:
            if self._closed or self._cancelled:
                return False
            if len(self._offered)>=2:
                raise ValueError('Too many speech parts')
            self._offered.append(text)
            observer = self._observer
            # The event-loop owner updates echo protection before the consumer
            # can synthesize this part. The observer never runs on that worker.
            if observer is not None:
                observer(text)
            self._pending.append(text)
            self._condition.notify_all()
        return True

    def observe(self, callback):
        if not callable(callback):
            raise ValueError('Expected speech observer')
        with self._condition:
            if self._observer is not None:
                raise ValueError('Speech observer already set')
            if self._cancelled:
                return
            for text in self._offered:
                callback(text)
            self._observer = callback

    def finish(self):
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def cancel(self):
        with self._condition:
            self._cancelled = True
            self._observer = None
            self._pending.clear()
            self._condition.notify_all()

    def __iter__(self):
        return self.consume(lambda:None)

    def consume(self, current):
        import time
        with self._condition:
            if self._consumer:
                raise ValueError('Speech parts already consumed')
            self._consumer = True
        while True:
            deadline = time.monotonic()+120
            current()
            with self._condition:
                while not self._pending and not self._closed and not self._cancelled:
                    remaining = deadline-time.monotonic()
                    if remaining<=0:
                        raise TimeoutError('Превышено время ожидания продолжения ответа')
                    self._condition.wait(min(.05,remaining))
                    current()
                if self._cancelled or not self._pending:
                    return
                text = self._pending.popleft()
            current()
            yield text


async def respond(process, play, current, shorten, cue, cue_after, *, play_parts=None):
    loop = asyncio.get_running_loop()
    offered = asyncio.Event()
    prefix = ''
    received = ''
    early = None
    parts = _SpeechParts() if play_parts is not None else None
    complete_offer = False
    using_parts = False
    async def speak(text):
        with request_flow.use(flow):
            return await play(text)
    async def first(text):
        nonlocal using_parts
        flow.mark('first_sentence_ready')
        if parts is not None and not complete_offer:
            using_parts = True
            parts.offer(text)
            with request_flow.use(flow):
                return await play_parts(parts)
        return await speak(text)
    def accept(text):
        nonlocal early
        if early is None and current():
            early = asyncio.create_task(first(text))
            offered.set()
    def delta(text):
        nonlocal received, prefix
        if prefix or len(received) > 1024:
            return
        received += text
        # Wait for a following word, so a decimal/version/abbreviation is not
        # spoken as a completed sentence. Code stays on the complete-reply path.
        boundary = re.search(r'(?<=[.!?…])\s+(?=[А-ЯЁA-Z«])', received)
        if boundary is not None:
            candidate = received[:boundary.start()].strip()
            if 12 <= len(candidate) <= 400 and not any(mark in candidate for mark in ('`', '#', '\n', '*', '|')):
                prefix = candidate
                loop.call_soon_threadsafe(accept, prefix)
    def completed(result):
        nonlocal prefix, complete_offer
        if prefix or not current():
            return
        text = result.get('response', '')
        if isinstance(text, str) and text.strip():
            prefix = text if result.get('type') == 'introduction' else shorten(text)
            if prefix:
                complete_offer = True
                loop.call_soon_threadsafe(accept, prefix)
    flow = request_flow.Flow(delta, kind='voice', valid=current, ready=completed)
    async def produce():
        with request_flow.use(flow):
            return await process()
    producer = asyncio.create_task(produce())
    waiting = asyncio.create_task(offered.wait())
    try:
        done, _ = await asyncio.wait({producer, waiting}, timeout=cue_after, return_when=asyncio.FIRST_COMPLETED)
        if not done and current():
            await cue()
        result = await producer
        # Let the last cross-thread offer reach the event loop before deciding
        # whether the full reply has already started speaking.
        await asyncio.sleep(0)
        response = result.get('response', '')
        if not response or not current():
            return result
        spoken = response if result.get('type') == 'introduction' else shorten(response)
        if early is not None and using_parts:
            if spoken.startswith(prefix):
                remaining = spoken[len(prefix):].strip()
                if remaining:
                    parts.offer(remaining)
            elif response.startswith('❌'):
                parts.offer('Ответ прервался. Попробуйте задать вопрос ещё раз.')
            parts.finish()
            await early
        elif early is not None:
            played = await early
            if not played or not current():
                return result
            if spoken.startswith(prefix):
                remaining = spoken[len(prefix):].strip()
                if remaining:
                    await speak(remaining)
            # Partial output is never replayed or silently replaced by another
            # model/voice. A later failure is stated separately.
            elif response.startswith('❌'):
                await speak('Ответ прервался. Попробуйте задать вопрос ещё раз.')
        else:
            await speak(spoken)
        return result
    finally:
        if parts is not None:
            parts.cancel()
        flow.mark('total')
        flow.cancelled.set()
        waiting.cancel()
        if not producer.done():
            producer.cancel()
        if early is not None and not early.done():
            early.cancel()
        await asyncio.gather(producer, waiting, *([early] if early else []), return_exceptions=True)
