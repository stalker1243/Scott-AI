"""Concurrent readiness requests share one isolated SDK probe, not model state."""
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
from threading import Barrier, Condition, Event

import pytest
import scott_voice_engine as engine

pytestmark=pytest.mark.unit


@pytest.fixture
def probe(monkeypatch):
    class Probe:
        def __init__(self):
            self.calls=[]
            self.condition=Condition()
            self.stops=[]

        def popen(self,command,**options):
            class Child:
                pid=2000000000  # No real process is signalled by these tests.
                returncode=0
                def __init__(self):
                    self.release=Event()
                    self.info=dict(ready=True,compatible=True,cuda=True)
                    self.error=None
                    self.timeouts=[]
                def communicate(self,timeout):
                    self.timeouts.append(timeout)
                    assert self.release.wait(4),'Test probe was not released'
                    if self.error is not None:
                        error,self.error=self.error,None
                        raise error
                    return json.dumps(self.info),''
            child=Child()
            with self.condition:
                self.calls.append(child)
                self.condition.notify_all()
            return child

        def wait(self,count,timeout=2):
            with self.condition:
                return self.condition.wait_for(lambda:len(self.calls)>=count,timeout)

        def release(self):
            with self.condition:
                for child in self.calls:child.release.set()

    state=Probe()
    engine._probe_runtime.cache_clear()
    monkeypatch.setattr(engine.subprocess,'Popen',state.popen)
    monkeypatch.setattr(engine,'stop_process_tree',lambda process,owner:state.stops.append(process))
    yield state
    state.release()
    engine._probe_runtime.cache_clear()


def requests(pool,count,**options):
    barrier=Barrier(count+1)
    def request():
        barrier.wait(timeout=3)
        return engine._probe_runtime('synthetic-sdk-python','cuda',**options)
    futures=[pool.submit(request) for _ in range(count)]
    barrier.wait(timeout=3)
    return futures


@pytest.mark.parametrize('count',[2,4,8])
def test_overlapping_readiness_starts_one_child(probe,count):
    with ThreadPoolExecutor(max_workers=count) as pool:
        futures=requests(pool,count,fingerprint='same-installation')
        try:
            assert probe.wait(1)
            assert not probe.wait(2,timeout=.15),'The same SDK was probed concurrently'
            assert all(not future.done() for future in futures)
        finally:probe.release()
        assert [future.result(timeout=3) for future in futures]==['']*count
    assert engine._probe_runtime('synthetic-sdk-python','cuda','same-installation')==''
    assert len(probe.calls)==1


@pytest.mark.parametrize('different',[
    ('other-sdk-python','cuda','same'),
    ('synthetic-sdk-python','cpu','same'),
    ('synthetic-sdk-python','cuda','changed-metadata'),
])
def test_distinct_installation_device_or_fingerprint_is_not_blocked(probe,different):
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(engine._probe_runtime,'synthetic-sdk-python','cuda','same')
        assert probe.wait(1)
        second=pool.submit(engine._probe_runtime,*different)
        try:assert probe.wait(2),'An unrelated SDK probe waited behind another installation'
        finally:probe.release()
        assert first.result(timeout=3)==second.result(timeout=3)==''
    assert len(probe.calls)==2


@pytest.mark.parametrize('info,expected',[
    (dict(ready=False,compatible=True,cuda=True),'runtime_unavailable'),
    (dict(ready=True,compatible=False,cuda=True),'runtime_update_required'),
    (dict(ready=True,compatible=True,cuda=False),'cuda_unavailable'),
])
def test_shared_failure_keeps_native_readiness_result(probe,info,expected):
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=requests(pool,2,fingerprint='unavailable')
        try:
            assert probe.wait(1)
            assert not probe.wait(2,timeout=.15)
            probe.calls[0].info=info
        finally:probe.release()
        assert [future.result(timeout=3) for future in futures]==[expected]*2
    assert engine._probe_runtime('synthetic-sdk-python','cuda','unavailable')==expected
    assert len(probe.calls)==1


def test_clear_during_active_probe_starts_fresh_check_and_keeps_new_result(probe):
    with ThreadPoolExecutor(max_workers=2) as pool:
        old=pool.submit(engine._probe_runtime,'synthetic-sdk-python','cuda','same')
        assert probe.wait(1)
        probe.calls[0].info['cuda']=False
        engine._probe_runtime.cache_clear()
        new=pool.submit(engine._probe_runtime,'synthetic-sdk-python','cuda','same')
        try:
            assert probe.wait(2),'Cache clear joined an obsolete in-flight check'
            probe.calls[1].release.set()
            assert new.result(timeout=3)==''
        finally:probe.release()
        assert old.result(timeout=3)=='cuda_unavailable'
    assert engine._probe_runtime('synthetic-sdk-python','cuda','same')==''
    assert len(probe.calls)==2


def test_shared_timeout_retains_deadlines_and_stops_one_owned_child(probe):
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=requests(pool,2,fingerprint='timeout')
        try:
            assert probe.wait(1)
            assert not probe.wait(2,timeout=.15)
            probe.calls[0].error=subprocess.TimeoutExpired('synthetic-sdk-python',15)
        finally:probe.release()
        assert [future.result(timeout=3) for future in futures]==['runtime_unavailable']*2
    assert probe.stops==probe.calls and len(probe.stops)==1
    assert probe.calls[0].timeouts==[15,3]


def test_unexpected_failure_reaches_waiters_and_does_not_leave_stuck_job(probe):
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=requests(pool,2,fingerprint='failure')
        try:
            assert probe.wait(1)
            assert not probe.wait(2,timeout=.15)
            probe.calls[0].error=RuntimeError('synthetic probe error')
        finally:probe.release()
        for future in futures:
            with pytest.raises(RuntimeError,match='synthetic probe error'):future.result(timeout=3)
        repeated=pool.submit(engine._probe_runtime,'synthetic-sdk-python','cuda','failure')
        try:assert probe.wait(2)
        finally:probe.release()
        assert repeated.result(timeout=3)==''
    assert len(probe.calls)==2


@pytest.mark.parametrize('old_finishes_first',[True,False])
def test_installation_cache_cannot_keep_a_pre_reset_probe_result(probe,tmp_path,monkeypatch,old_finishes_first):
    from test_scott_voice_engine import installed_assets
    native_probe=engine._probe_runtime
    config=installed_assets.__wrapped__(tmp_path,monkeypatch)
    monkeypatch.setattr(engine,'_probe_runtime',native_probe)
    engine.inspect_installation.cache_clear()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            old=pool.submit(engine.inspect_installation,config)
            assert probe.wait(1)
            probe.calls[0].info['cuda']=False
            engine.inspect_installation.cache_clear()
            engine._probe_runtime.cache_clear()
            new=pool.submit(engine.inspect_installation,config)
            try:
                assert probe.wait(2)
                if old_finishes_first:
                    probe.calls[0].release.set()
                    assert old.result(timeout=3)=='cuda_unavailable'
                    probe.calls[1].release.set()
                    assert new.result(timeout=3)==''
                else:
                    probe.calls[1].release.set()
                    assert new.result(timeout=3)==''
                    probe.calls[0].release.set()
                    assert old.result(timeout=3)=='cuda_unavailable'
            finally:probe.release()
        assert engine.inspect_installation(config)==''
        assert len(probe.calls)==2
    finally:engine.inspect_installation.cache_clear()
