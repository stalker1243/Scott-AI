"""Preparation controls with fake models; never open audio or user stores."""
import threading
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import scott_voice_engine as engine
from scott_voice_process import VoiceProcessError
import voice_prepare
import voice_prepare_endpoints as endpoints

pytestmark=pytest.mark.unit


@pytest.fixture
def control(tmp_path, monkeypatch):
    monkeypatch.setattr(engine,'inspect_installation',lambda _: '')
    started, release = threading.Event(), threading.Event()
    class Client:
        def __init__(self,*args,**kwargs):
            self.loaded=False
            self.active=False
            self.closed=False
        def prepare(self):
            self.active=True
            started.set()
            release.wait(3)
            self.active=False
            if self.closed: raise VoiceProcessError('cancelled')
            self.loaded=True
            return self.status()
        def status(self): return dict(model_loaded=self.loaded and not self.closed,active=self.active)
        def close(self):
            self.closed=True
            release.set()
    model=engine.ScottVoiceEngine(engine.default_config(tmp_path),Client)
    manager=voice_prepare.VoicePreparation(lambda:model)
    yield SimpleNamespace(manager=manager,engine=model,started=started,release=release)
    manager.close()
    model.close()


def test_manual_start_returns_while_model_loads_and_blocks_duplicate(control):
    state=control.manager.start()
    assert state['state']=='running' and control.started.wait(1)
    with pytest.raises(voice_prepare.PrepareConflict): control.manager.start()
    control.release.set()
    control.manager._thread.join(2)
    assert control.manager.snapshot()['model_loaded']
    assert control.manager.snapshot()['state']=='complete'
    control.engine._client.loaded=False  # Simulate the idle worker releasing memory.
    assert control.manager.snapshot()['state']=='idle'


def test_cancel_active_prepare_and_release_complete_model(control):
    first=control.manager.start()
    assert control.started.wait(1)
    control.manager.cancel(first['id'])
    control.manager._thread.join(2)
    assert control.manager.snapshot()['state']=='cancelled'
    second=control.manager.start()
    control.manager._thread.join(2)
    assert control.manager.snapshot()['model_loaded']
    with pytest.raises(voice_prepare.PrepareConflict): control.manager.cancel(first['id'])
    control.manager.cancel(second['id'])
    assert not control.manager.snapshot()['model_loaded']


def test_old_cancel_does_not_stop_replacement_engine_generation(control):
    control.release.set()
    state=control.manager.start()
    control.manager._thread.join(2)
    control.engine.cancel()
    control.engine.prepare()
    fresh=control.engine._client
    control.manager.cancel(state['id'])
    assert not fresh.closed and fresh.loaded


def test_new_voice_command_keeps_idle_prepared_model_and_generation(control,monkeypatch):
    import audio_endpoints
    import speech_player
    control.release.set()
    state=control.manager.start()
    control.manager._thread.join(2)
    client=control.engine._client
    generation=control.engine.generation
    stopped=[]
    monkeypatch.setattr(engine,'_engine',control.engine)
    monkeypatch.setattr(speech_player,'get_player',lambda:SimpleNamespace(stop=lambda:stopped.append(True)))
    monkeypatch.setattr(speech_player,'PLAYBACK_AVAILABLE',True)
    audio_endpoints._stop_current_speech(preserve_prepared=True)
    assert stopped==[True] and not client.closed
    assert control.engine.generation==generation
    assert control.manager.snapshot()['model_loaded']
    control.manager.cancel(state['id'])
    assert client.closed


def test_new_request_cancels_active_preparation(control):
    state=control.manager.start()
    assert control.started.wait(1)
    control.engine.cancel(preserve_idle=True)
    control.manager._thread.join(2)
    assert control.manager.snapshot()['state']=='cancelled'
    assert control.engine._client is None and control.engine._requests==0


def test_idle_preservation_cancels_request_waiting_before_client_entry(control,monkeypatch):
    control.release.set()
    control.engine.prepare()
    client=control.engine._client
    entered, release=threading.Event(),threading.Event()
    def waiting(*args):
        entered.set();assert release.wait(2)
        if client.closed: raise VoiceProcessError('cancelled')
        return SimpleNamespace(path='fake.wav')
    client.synthesize=waiting
    result=[]
    def request():
        try:control.engine.synthesize('Синтетическая проверка.')
        except VoiceProcessError as error:result.append(error.code)
    thread=threading.Thread(target=request)
    thread.start();assert entered.wait(1)
    assert client.status()['active'] is False and client.status()['model_loaded']
    control.engine.cancel(preserve_idle=True)
    release.set();thread.join(2)
    assert result==['cancelled'] and client.closed and control.engine._requests==0


def test_unavailable_or_busy_model_does_not_start_job(control,monkeypatch):
    monkeypatch.setattr(engine,'inspect_installation',lambda _:'not_installed')
    with pytest.raises(ValueError): control.manager.start()
    assert control.engine._client is None
    monkeypatch.setattr(engine,'inspect_installation',lambda _:'')
    control.engine._client=control.engine.factory()
    control.engine._client.active=True
    with pytest.raises(voice_prepare.PrepareConflict): control.manager.start()


def test_model_failure_is_reported_without_exception_payload(control,monkeypatch):
    def fail(**kwargs): raise RuntimeError('sensitive exception payload')
    monkeypatch.setattr(control.engine,'prepare',fail)
    control.manager.start()
    control.manager._thread.join(2)
    assert control.manager.snapshot()['state']=='failed'
    assert 'sensitive' not in control.manager.snapshot()['message']


def test_api_start_cancel_validation_and_nonblocking_status(control,monkeypatch):
    monkeypatch.setattr(endpoints,'preparation',control.manager)
    app=FastAPI();app.include_router(endpoints.router)
    with TestClient(app) as api:
        assert api.get('/voice/prepare').json()['state']=='idle'
        assert api.post('/voice/prepare',json={'text':'no commands'}).status_code==422
        state=api.post('/voice/prepare',json={}).json()
        assert state['state']=='running'
        assert api.get('/voice/prepare').status_code==200
        assert api.post('/voice/prepare',json={}).status_code==409
        assert api.post('/voice/prepare/cancel',json={'id':'bad'}).status_code==422
        assert api.post('/voice/prepare/cancel',json={'id':'0'*32}).status_code==409
        assert api.post('/voice/prepare/cancel',json={'id':state['id']}).status_code==200
        control.manager._thread.join(2)
        assert api.get('/voice/prepare').json()['model_loaded'] is False
