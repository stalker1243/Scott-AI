"""Microphone-triggered preparation with synthetic listeners/models, no devices."""
from types import SimpleNamespace
import threading
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import audio_settings
import listen_endpoints
import scott_voice_engine as engine
import voice_prepare_endpoints
from scott_voice_process import VoiceProcessError
from test_voice_prepare import control

pytestmark=pytest.mark.unit


def wait_for(predicate):
    deadline=time.monotonic()+2
    while time.monotonic()<deadline:
        if predicate():return
        time.sleep(.01)
    raise AssertionError('Expected preparation state not reached')


@pytest.fixture(autouse=True)
def audible(monkeypatch):
    monkeypatch.setattr(audio_settings,'is_quiet',lambda:False)


def activate(manager):
    return manager.start_listening(manager.listening_requested())


def test_listening_start_and_status_do_not_wait_for_native_probe(control,monkeypatch):
    entered,release=threading.Event(),threading.Event()
    describe=control.engine.describe
    def blocked():
        entered.set();assert release.wait(3)
        return describe()
    monkeypatch.setattr(control.engine,'describe',blocked)
    started=time.monotonic();state=activate(control.manager)
    try:
        assert time.monotonic()-started<.5
        assert state['state']=='running' and entered.wait(1)
        assert control.manager.snapshot()['state']=='running'
        ident=control.manager.listening_stopped()
        control.manager.cancel_listening(ident)
        assert control.engine._client is None
    finally:release.set()
    control.manager._thread.join(2)
    assert not control.started.is_set() and control.manager.snapshot()['state']=='cancelled'


def test_quiet_start_allocates_no_engine(control,monkeypatch):
    monkeypatch.setattr(audio_settings,'is_quiet',lambda:True)
    monkeypatch.setattr(control.manager,'provider',lambda:pytest.fail('Quiet microphone needs no TTS engine'))
    activate(control.manager);control.manager._thread.join(2)
    assert control.manager.snapshot()['state']=='idle' and control.engine._client is None


def test_duplicate_start_and_loaded_model_reuse_one_prepare(control,monkeypatch):
    calls=[]
    original=control.engine.prepare
    def prepare(**kwargs):calls.append(kwargs);return original(**kwargs)
    monkeypatch.setattr(control.engine,'prepare',prepare)
    state=activate(control.manager)
    assert control.started.wait(1)
    assert activate(control.manager)['id']==state['id']
    control.release.set();control.manager._thread.join(2)
    client=control.engine._client
    activate(control.manager);control.manager._thread.join(2)
    assert calls==[dict(generation=0,for_listening=True)]
    assert control.engine._client is client and control.manager.snapshot()['model_loaded']


def test_first_command_preserves_active_automatic_prepare(control,monkeypatch):
    import audio_endpoints,speech_player
    activate(control.manager);assert control.started.wait(1)
    client=control.engine._client;generation=control.engine.generation
    monkeypatch.setattr(engine,'_engine',control.engine)
    monkeypatch.setattr(speech_player,'PLAYBACK_AVAILABLE',False)
    audio_endpoints._stop_current_speech(preserve_prepared=True)
    assert not client.closed and control.engine.generation==generation
    control.release.set();control.manager._thread.join(2)
    client.synthesize=lambda *a:SimpleNamespace(path='synthetic.wav')
    assert control.engine.synthesize('Проверка.')=='synthetic.wav'
    assert control.engine._client is client and control.engine._listening_prepares==0


def test_first_command_during_native_check_does_not_restart_preparation(control,monkeypatch):
    entered,release=threading.Event(),threading.Event()
    describe=control.engine.describe
    def blocked():entered.set();assert release.wait(3);return describe()
    monkeypatch.setattr(control.engine,'describe',blocked)
    activate(control.manager);assert entered.wait(1)
    generation=control.engine.generation
    control.engine.cancel(preserve_idle=True)
    assert control.engine.generation==generation
    release.set();assert control.started.wait(1)
    control.release.set();control.manager._thread.join(2)
    assert control.manager.snapshot()['model_loaded'] and not control.engine._listening_warmups


def test_interrupt_still_cancels_auto_prepare_with_queued_speech(control):
    activate(control.manager);assert control.started.wait(1)
    client=control.engine._client
    entered,release=threading.Event(),threading.Event()
    def synthesize(*args):
        entered.set();assert release.wait(2)
        if client.closed:raise VoiceProcessError('cancelled')
        return SimpleNamespace(path='synthetic.wav')
    client.synthesize=synthesize
    failures=[]
    def speak():
        try:control.engine.synthesize('Проверка.')
        except VoiceProcessError as error:failures.append(error.code)
    thread=threading.Thread(target=speak);thread.start()
    assert entered.wait(1)
    control.engine.cancel(preserve_idle=True)
    release.set();thread.join(2);control.manager._thread.join(2)
    assert failures==['cancelled'] and client.closed
    assert control.engine._requests==control.engine._listening_prepares==0


def test_stop_releases_automatic_model_and_stale_start_does_nothing(control):
    epoch=control.manager.listening_requested()
    control.manager.start_listening(epoch);assert control.started.wait(1)
    client=control.engine._client
    control.manager.cancel_listening(control.manager.listening_stopped())
    control.manager._thread.join(2)
    control.manager.start_listening(epoch)
    assert client.closed and control.manager.snapshot()['state']=='cancelled'
    assert not control.manager.snapshot()['model_loaded']


def test_stop_then_start_during_probe_keeps_latest_start(control,monkeypatch):
    entered,release=threading.Event(),threading.Event()
    describe=control.engine.describe
    def blocked():entered.set();assert release.wait(3);return describe()
    monkeypatch.setattr(control.engine,'describe',blocked)
    old=activate(control.manager);assert entered.wait(1)
    ident=control.manager.listening_stopped()
    control.manager.cancel_listening(ident)
    latest=control.manager.listening_requested()
    control.manager.start_listening(latest)
    control.release.set();release.set()
    wait_for(lambda:control.manager.snapshot()['state']=='complete')
    assert control.manager.snapshot()['id']!=old['id'] and control.manager.snapshot()['model_loaded']
    assert control.engine._requests==control.engine._listening_prepares==0


def test_old_stop_cannot_cancel_new_manual_preparation(control):
    activate(control.manager);assert control.started.wait(1)
    old=control.manager.listening_stopped()
    control.release.set();control.manager._thread.join(2)
    state=control.manager.start();control.manager._thread.join(2)
    client=control.engine._client
    control.manager.cancel_listening(old)
    assert state['id']!=old and not client.closed and control.manager.snapshot()['model_loaded']


def test_cancel_manual_validation_before_it_allocates_model(control,monkeypatch):
    entered,release=threading.Event(),threading.Event()
    describe=control.engine.describe
    def blocked():entered.set();assert release.wait(3);return describe()
    monkeypatch.setattr(control.engine,'describe',blocked)
    thread=threading.Thread(target=control.manager.start);thread.start();assert entered.wait(1)
    control.manager.cancel(control.manager.snapshot()['id'])
    release.set();thread.join(2)
    assert control.engine._client is None and control.manager.snapshot()['state']=='cancelled'


@pytest.fixture
def api(control,monkeypatch):
    class Listener:
        def __init__(self):self.running=False;self.fail=False
        def start(self):
            self.running=not self.fail
            return dict(success=not self.fail,message='synthetic microphone')
        def stop(self):self.running=False;return dict(success=True)
        def status(self):return dict(listening=self.running,available=True)
    listener=Listener()
    monkeypatch.setattr(listen_endpoints.scott_runtime,'listener',listener)
    monkeypatch.setattr(listen_endpoints,'_voice_preparation',lambda:control.manager)
    monkeypatch.setattr(voice_prepare_endpoints,'preparation',control.manager)
    app=FastAPI();app.include_router(listen_endpoints.router);app.include_router(voice_prepare_endpoints.router)
    @app.get('/health')
    def health():return {'ok':True}
    with TestClient(app) as client:yield SimpleNamespace(client=client,listener=listener)


def test_listen_api_starts_microphone_while_model_loads_and_stop_cancels(api,control):
    result=api.client.post('/listen/start').json()
    assert result['success'] and result['listening'] and control.started.wait(1)
    assert result['voice_preparation']['state']=='running'
    assert api.client.get('/health').status_code==200
    assert api.client.get('/voice/prepare').json()['state']=='running'
    stopped=api.client.post('/listen/stop').json()
    control.manager._thread.join(2)
    assert stopped['success'] and not stopped['listening']
    assert not control.manager.snapshot()['model_loaded']


def test_failed_microphone_start_does_not_prepare_model(api,control,monkeypatch):
    api.listener.fail=True
    monkeypatch.setattr(control.manager,'provider',lambda:pytest.fail('Failed microphone must not load TTS'))
    assert api.client.post('/listen/start').status_code==503
    assert control.manager.snapshot()['state']=='idle' and control.engine._client is None


def test_missing_listener_stop_still_cancels_pending_model(api,control,monkeypatch):
    assert api.client.post('/listen/start').json()['listening'] and control.started.wait(1)
    client=control.engine._client
    monkeypatch.setattr(listen_endpoints.scott_runtime,'listener',None)
    assert api.client.post('/listen/stop').status_code==503
    control.manager._thread.join(2)
    assert client.closed and control.manager.snapshot()['state']=='cancelled'


def test_unavailable_voice_keeps_listening_and_reports_reason(api,control,monkeypatch):
    monkeypatch.setattr(engine,'inspect_installation',lambda _:'not_installed')
    assert api.client.post('/listen/start').json()['listening']
    control.manager._thread.join(2)
    state=api.client.get('/voice/prepare').json()
    assert state['state']=='failed' and state['message']==engine.MESSAGES['not_installed']
    assert api.client.get('/listen/status').json()['listening'] and control.engine._client is None


def test_new_listening_epoch_survives_old_failed_start(control):
    old=control.manager.listening_requested()
    new=control.manager.listening_requested()
    assert control.manager.listening_failed(old) is None
    control.release.set();control.manager.start_listening(new);control.manager._thread.join(2)
    assert control.manager.snapshot()['model_loaded']


def test_unknown_provider_error_is_not_exposed(api,control,monkeypatch):
    def fail():raise ValueError('sensitive provider payload')
    monkeypatch.setattr(control.manager,'provider',fail)
    assert api.client.post('/listen/start').json()['listening']
    control.manager._thread.join(2)
    state=control.manager.snapshot()
    assert state['state']=='failed' and 'sensitive' not in state['message']
