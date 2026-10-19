import json
import subprocess
from types import SimpleNamespace
import pytest
import desktop_control as control

pytestmark=pytest.mark.unit


@pytest.fixture
def desktop(monkeypatch):
    monkeypatch.delenv('SCOTT_DESKTOP_DISABLED',raising=False)
    windows=[dict(id='0x11',pid=101,app='Firefox.exe',title='First document — Firefox'),
             dict(id='0x22',pid=102,app='Telegram.exe',title='Telegram'),
             dict(id='0x33',pid=103,app='Firefox.exe',title='Second document — Firefox')]
    sent=[]
    def worker(spec):
        sent.append(spec)
        if spec['operation']=='list':return dict(success=True,windows=windows,active='0x22')
        return dict(success=True,accepted=[row['id'] for row in spec['targets']],failed=[])
    monkeypatch.setattr(control,'_worker',worker)
    return windows,sent


def test_close_all_is_scoped_excludes_named_apps_and_only_sends_graceful_close(desktop):
    windows,sent=desktop
    result=control.execute(dict(operation='close_all',exclude=['Firefox']))
    assert result['success'] and result['requested']==1
    assert sent[-1]['operation']=='close' and sent[-1]['targets']==[dict(id='0x22',pid=102)]
    assert 'сохранить' in result['response']
    sent.clear()
    assert control.execute(dict(operation='close_all'),scope_pids={103})['requested']==1
    assert sent[-1]['targets']==[dict(id='0x33',pid=103)]


def test_ambiguous_window_never_invokes_any_action(desktop):
    _,sent=desktop
    result=control.execute(dict(operation='focus',query='Firefox'))
    assert not result['success'] and result['code']=='ambiguous'
    assert len(sent)==1
    assert control.execute(dict(operation='focus',query='Second document — Firefox'))['success']
    assert sent[-1]['targets']==[dict(id='0x33',pid=103)]


def test_current_window_and_named_app_close(desktop):
    _,sent=desktop
    assert control.execute(dict(operation='minimize'))['success']
    assert sent[-1]['operation']=='minimize' and sent[-1]['targets'][0]['pid']==102
    assert control.execute(dict(operation='close_app',query='Firefox'))['requested']==2


def test_accessibility_requires_selected_window_and_passes_literal_control(desktop,monkeypatch):
    import desktop_accessibility
    received=[]
    def invoke(op,window,label,env):
        received.append((op,window,label,env));return dict(success=True,invoked=True)
    monkeypatch.setattr(desktop_accessibility,'run',invoke)
    monkeypatch.setenv('OPENAI_API_KEY','fixture-secret')
    monkeypatch.setenv('SCOTT_RUNTIME_TOKEN','fixture-runtime')
    assert control.execute(dict(operation='invoke',query='Telegram',control="Play; $(bad)"))['success']
    assert received[0][:3]==('invoke',desktop[0][1],"Play; $(bad)")
    assert 'OPENAI_API_KEY' not in received[0][3] and 'SCOTT_RUNTIME_TOKEN' not in received[0][3]


def test_lost_worker_or_invalid_message_is_nonfatal(monkeypatch):
    monkeypatch.setattr(control.subprocess,'run',lambda *args,**kw:SimpleNamespace(stdout=b'invalid',returncode=-1))
    assert control._worker(dict(operation='list'))['code']=='worker_failed'
    def timeout(*args,**kwargs):raise subprocess.TimeoutExpired('fixture',8)
    monkeypatch.setattr(control.subprocess,'run',timeout)
    assert control._worker(dict(operation='list'))['code']=='timeout'


def test_unit_environment_disables_os_access(monkeypatch):
    monkeypatch.setenv('SCOTT_DESKTOP_DISABLED','1')
    monkeypatch.setattr(control,'_worker',lambda *args:pytest.fail('Must not access real windows'))
    assert control.execute(dict(operation='close_all'))['code']=='disabled'


@pytest.mark.parametrize('payload',[None,{},dict(operation='terminate_all'),dict(operation='focus',query='x'*513)])
def test_invalid_requests_are_bounded_and_nonfatal(desktop,payload):
    assert not control.execute(payload)['success']


def test_legacy_button_fallback_only_before_any_possible_invocation(desktop,monkeypatch):
    import desktop_accessibility
    monkeypatch.setattr(control,'os',SimpleNamespace(name='nt',environ={}))
    monkeypatch.setattr(control,'own_pids',lambda:[])
    sent=desktop[1]
    worker=control._worker
    def native(spec):
        if spec['operation']=='invoke':
            sent.append(spec);return dict(success=True,invoked=True,provider='win32-control')
        if spec['operation']=='controls':
            sent.append(spec);return dict(success=True,controls=['Play'],provider='win32-control')
        return worker(spec)
    monkeypatch.setattr(control,'_worker',native)
    monkeypatch.setattr(desktop_accessibility,'run',lambda *args:dict(success=True,controls=[]))
    assert control.execute(dict(operation='controls',query='Telegram'))['provider']=='win32-control'
    for code in ('no_control','no_pattern'):
        monkeypatch.setattr(desktop_accessibility,'run',lambda *args,code=code:dict(success=False,code=code))
        assert control.execute(dict(operation='invoke',query='Telegram',control='Play'))['success']
    for code in ('timeout','invoke_failed','ambiguous','window_changed','provider_unavailable'):
        sent.clear()
        monkeypatch.setattr(desktop_accessibility,'run',lambda *args,code=code:dict(success=False,code=code))
        assert not control.execute(dict(operation='invoke',query='Telegram',control='Play'))['success']
        assert [row['operation'] for row in sent]==['list']
