import asyncio
import contextvars
import threading
import time

import pytest
from bounded_work import WorkPool, WorkBusy, WorkTimeout

pytestmark = pytest.mark.unit


def test_timeout_retains_slot_and_late_exception_is_consumed():
    pool = WorkPool(1, 'fixture-timeout'); release = threading.Event(); started = threading.Event()
    stopped = threading.Event(); completions = []
    def stuck():
        started.set(); release.wait(3); stopped.set(); raise ValueError('late fixture failure')
    async def check():
        try:
            with pytest.raises(WorkTimeout):
                await pool.run(stuck, timeout=.04, completion=lambda: completions.append('done'))
            assert started.is_set() and completions == []
            with pytest.raises(WorkBusy):
                await pool.run(lambda: 2, timeout=1)
        finally:
            release.set()
        deadline = time.monotonic()+2
        while not completions and time.monotonic()<deadline:
            await asyncio.sleep(.005)
        assert completions == ['done']
        assert await pool.run(lambda: 7, timeout=1) == 7
    try: asyncio.run(check())
    finally: release.set();pool.close()


def test_cancellation_keeps_running_work_bounded_and_signals_cancel_event():
    pool=WorkPool(1,'fixture-cancel'); release=threading.Event(); started=threading.Event(); cancelled=threading.Event()
    def job(): started.set();release.wait(3)
    async def check():
        task=asyncio.create_task(pool.run(job,timeout=2,cancelled=cancelled))
        while not started.is_set(): await asyncio.sleep(.005)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert cancelled.is_set()
        with pytest.raises(WorkBusy): await pool.run(lambda: None)
    try: asyncio.run(check())
    finally: release.set();pool.close()


def test_context_and_pool_work_across_separate_event_loops():
    pool=WorkPool(1,'fixture-context'); value=contextvars.ContextVar('fixture-value',default='missing')
    async def check(expected):
        value.set(expected)
        return await pool.run(value.get,timeout=1)
    try:
        assert asyncio.run(check('first'))=='first'
        assert asyncio.run(check('second'))=='second'
    finally: pool.close()


def test_failed_job_and_admission_release_their_own_reservations():
    pool=WorkPool(1,'fixture-failure'); completed=[]
    def fail(): raise OSError('fixture')
    async def check():
        with pytest.raises(OSError): await pool.run(fail,completion=lambda: completed.append(1))
        assert completed==[1]
        assert await pool.run(lambda: 9)==9
        pool.close()
        with pytest.raises(RuntimeError): await pool.run(lambda: 1,completion=lambda: completed.append(2))
        assert completed==[1,2]
    asyncio.run(check())


def test_many_timeouts_do_not_create_unbounded_workers():
    pool=WorkPool(2,'fixture-limit'); release=threading.Event(); began=[]
    def job(): began.append(1);release.wait(3)
    async def check():
        results=await asyncio.gather(*(pool.run(job,timeout=.03) for _ in range(2)),return_exceptions=True)
        assert all(isinstance(row,WorkTimeout) for row in results)
        for _ in range(12):
            with pytest.raises(WorkBusy): await pool.run(job,timeout=.01)
        assert len(began)==2
        tick=asyncio.Event();asyncio.get_running_loop().call_soon(tick.set)
        await asyncio.wait_for(tick.wait(),.2)
    try: asyncio.run(check())
    finally: release.set();pool.close()
