"""SSE transport with backpressure and request cancellation, including disconnects."""
import asyncio
import json
import time
from concurrent.futures import TimeoutError as FutureTimeout
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
try:
    from . import request_flow
    from .api_boundary import error_response
except ImportError:
    import request_flow
    from api_boundary import error_response

def response(work, scope):
    async def body():
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue(maxsize=32)
        def emit(text):
            flow.check()
            pending = asyncio.run_coroutine_threadsafe(queue.put(text), loop)
            try:
                while True:
                    try:
                        pending.result(.1)
                        return
                    except FutureTimeout:
                        flow.check()
            finally:
                if not pending.done():
                    pending.cancel()
        flow = request_flow.Flow(emit=emit, timeout=200)
        async def run():
            with request_flow.use(flow):
                return await work()
        task = asyncio.create_task(run())
        heartbeat = time.monotonic()
        def event(kind, value):
            return 'event: ' + kind + '\ndata: ' + json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n\n'
        try:
            while True:
                if task.done() and queue.empty():
                    try:
                        yield event('done', task.result())
                    except Exception as error:
                        status = error.status_code if isinstance(error, HTTPException) else 500
                        safe = error_response(status, scope, getattr(error, 'detail', None))
                        yield event('error', json.loads(safe.body))
                    break
                try:
                    delta = await asyncio.wait_for(queue.get(), timeout=.1)
                    yield event('delta', {'text':delta})
                except asyncio.TimeoutError:
                    if time.monotonic() - heartbeat >= 5:
                        yield ': keepalive\n\n'
                        heartbeat = time.monotonic()
        finally:
            flow.mark('total')
            flow.cancelled.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    return StreamingResponse(body(), media_type='text/event-stream',
                             headers={'Cache-Control':'no-store', 'X-Accel-Buffering':'no'})
