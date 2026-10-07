"""Job state and API contracts use a tiny installer in a temporary root."""
import json
import time
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import voice_install_jobs as jobs
import voice_install_endpoints as endpoints
import scott_voice_engine as engine

pytestmark = pytest.mark.unit

@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.delenv('SCOTT_VOICE_HOME', raising=False)
    path = tmp_path/'backend/scott_voice_install.py'
    path.parent.mkdir()
    path.write_text('''import json,sys,time
print(json.dumps(dict(type='progress',stage='libraries',message='untrusted',fraction=0.99)),flush=True)
print('ignored non JSON log',flush=True)
if '--check' in sys.argv:
    time.sleep(.3)
    print(json.dumps(dict(type='result',available=True)),flush=True)
else:
    sys.stdin.readline()
    print(json.dumps(dict(type='error',cancelled=True)),flush=True)
    sys.exit(3)
''', encoding='utf-8')
    refreshed = []
    manager = jobs.VoiceInstallJobs(tmp_path, refresh=lambda: refreshed.append(True))
    manager.refreshed = refreshed
    yield manager
    manager.close()

def test_check_is_async_and_refreshes_catalog(manager):
    start = time.monotonic()
    state = manager.start('check')
    assert time.monotonic()-start < 1
    assert state['state'] == 'running'
    manager._thread.join(timeout=5)
    assert manager.snapshot()['state'] == 'complete'
    assert manager.refreshed == [True]
    assert not manager.home.exists()


@pytest.mark.skipif(jobs.os.name != 'nt', reason='Windows installation')
def test_update_quiesces_voice_before_starting_installer_but_check_does_not(manager):
    events=[]
    spawn=manager.popen
    manager.before_update=lambda:events.append('quiesce')
    def popen(*args,**kwargs):
        events.append('spawn')
        return spawn(*args,**kwargs)
    manager.popen=popen
    manager.start('check');manager._thread.join(timeout=5)
    assert events==['spawn']
    state=manager.start('install')
    assert events==['spawn','quiesce','spawn']
    manager.cancel(state['id']);manager._thread.join(timeout=5)
    assert manager.snapshot()['state']=='cancelled'

@pytest.mark.skipif(jobs.os.name != 'nt', reason='Windows installation')
def test_cancel_duplicate_and_retry(manager):
    first = manager.start('install')
    with pytest.raises(jobs.JobConflict):
        manager.start('check')
    with pytest.raises(jobs.JobConflict):
        manager.cancel('a'*32)
    assert manager.cancel(first['id'])['state'] == 'cancelling'
    manager._thread.join(timeout=5)
    assert manager.snapshot()['state'] == 'cancelled'
    assert manager.refreshed == []
    second = manager.start('check')
    assert second['id'] != first['id']
    with pytest.raises(jobs.JobConflict):
        manager.cancel(first['id'])
    manager._thread.join(timeout=5)
    assert manager.snapshot()['state'] == 'complete'

def test_api_rejects_paths_commands_and_old_job(manager, monkeypatch):
    monkeypatch.setattr(endpoints, 'jobs', manager)
    app = FastAPI(); app.include_router(endpoints.router)
    with TestClient(app) as client:
        assert client.get('/voice/install').json()['state'] == 'idle'
        for payload in ({'action':'execute'}, {'action':'install','home':'C:/private'},
                        {'action':'check','command':['cmd.exe']}):
            assert client.post('/voice/install', json=payload).status_code == 422
        state = client.post('/voice/install', json={'action':'check'}).json()
        assert state['state'] == 'running'
        assert client.post('/voice/install', json={'action':'check'}).status_code == 409
        assert client.post('/voice/install/cancel', json={'id':'invalid'}).status_code == 422
        assert client.post('/voice/install/cancel', json={'id':'f'*32}).status_code == 409
        assert client.get('/voice/install').status_code == 200

def test_invalid_markers_are_safe(manager):
    manager.home.mkdir()
    for marker in ([], None, {}, {'ready':True}, {'ready':'true'}):
        (manager.home/'scott-install.json').write_text(json.dumps(marker))
        assert manager.snapshot()['installed'] is False

def test_reload_closes_old_engine_and_discards_cached_probe(monkeypatch):
    class Old:
        closed = False
        def close(self): self.closed = True
    old = Old()
    monkeypatch.setattr(engine, '_engine', old)
    engine.reload_installation()
    assert old.closed and engine._engine is None
    assert engine.inspect_installation.cache_info().currsize == 0
