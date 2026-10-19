"""Optional component retries and isolated version probes; no real browser or network."""
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
import browser_setup as setup
from browser_control_config import installed

pytestmark=pytest.mark.unit


@pytest.fixture
def home(tmp_path,monkeypatch):
    (tmp_path/'libraries/playwright').mkdir(parents=True)
    (tmp_path/'libraries/playwright/__init__.py').write_text('')
    (tmp_path/'profile').mkdir()
    (tmp_path/'profile/preserved').write_bytes(b'profile bytes')
    (tmp_path/'settings.json').write_text('{"enabled":false}')
    monkeypatch.setattr(setup,'append_log',lambda *args:None)
    return tmp_path


def probe_result(home,version=None):
    return SimpleNamespace(returncode=0,stdout=json.dumps(dict(version=version or setup.VERSION,
        browser_executable=str(home/'browsers/chromium-test/chrome'))))


def test_retry_after_chromium_failure_keeps_ready_libraries_without_a_marker(home,monkeypatch,capsys):
    calls=[]; failed=False
    def run(command,**kwargs):
        nonlocal failed
        calls.append(command)
        if command[2]==setup.LIBRARY_PROBE:
            return probe_result(home)
        assert 'pip' not in command
        if not failed:
            failed=True
            kwargs['stdout'].write('getaddrinfo failed\n')
            return SimpleNamespace(returncode=1)
        executable=home/'browsers/chromium-test/chrome'
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b'cached browser')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(setup.subprocess,'run',run)
    monkeypatch.setattr(setup,'browser_options',lambda _: {})
    with pytest.raises(setup.SetupFailure) as error:
        setup.prepare(home)
    assert error.value.code=='network_unavailable' and not installed(home)
    setup.prepare(home)
    assert installed(home) and len(calls)==4
    assert all('pip' not in call for call in calls)
    assert (home/'profile/preserved').read_bytes()==b'profile bytes'
    assert (home/'settings.json').read_text()=='{"enabled":false}'
    event=json.loads(capsys.readouterr().out.splitlines()[-1])
    assert event['reused_libraries'] and event['browser']=='bundled'
    assert 'getaddrinfo failed' in (home/'setup.log').read_text()


def test_outdated_probe_repairs_only_optional_libraries(home,monkeypatch,capsys):
    calls=[]
    def run(command,**kwargs):
        calls.append(command)
        return probe_result(home,'0.0.0' if len(calls)==1 else setup.VERSION)
    monkeypatch.setattr(setup.subprocess,'run',run)
    monkeypatch.setattr(setup,'browser_options',lambda _: {'channel':'msedge'})
    setup.prepare(home)
    assert len(calls)==3 and 'pip' in calls[1]
    assert '--target' in calls[1] and str(home/'libraries') in calls[1]
    assert '--no-cache-dir' in calls[1] and '--only-binary=:all:' in calls[1]
    assert f'playwright=={setup.VERSION}' in calls[1]
    assert not json.loads(capsys.readouterr().out.splitlines()[-1])['reused_libraries']


@pytest.mark.parametrize('error,code',[(subprocess.TimeoutExpired('probe',30),'timeout'),
                                    (PermissionError(13,'denied'),'permission_denied')])
def test_local_probe_failure_does_not_trigger_download(home,monkeypatch,error,code):
    calls=[]
    def run(command,**kwargs):
        calls.append(command)
        raise error
    monkeypatch.setattr(setup.subprocess,'run',run)
    with pytest.raises(setup.SetupFailure) as failed:
        setup.prepare(home)
    assert failed.value.code==code and len(calls)==1 and 'pip' not in calls[0]
    assert not installed(home)


def test_old_network_error_is_not_reused_as_the_cause_of_a_new_failure(home,monkeypatch):
    (home/'setup.log').write_text('ReadTimeoutError: timed out\n')
    def run(command,**kwargs):
        if command[2]==setup.LIBRARY_PROBE:
            return probe_result(home)
        kwargs['stdout'].write('Unsupported platform\n')
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(setup.subprocess,'run',run)
    monkeypatch.setattr(setup,'browser_options',lambda _: {})
    with pytest.raises(setup.SetupFailure) as failed:
        setup.prepare(home)
    assert failed.value.code=='process_failed'
    assert 'Chromium' in str(failed.value) and 'интернет' not in str(failed.value)
    assert 'Unsupported platform' in (home/'setup.log').read_text()


def test_successful_cli_without_a_browser_does_not_publish_ready(home,monkeypatch):
    monkeypatch.setattr(setup.subprocess,'run',lambda *args,**kwargs:probe_result(home))
    monkeypatch.setattr(setup,'browser_options',lambda _: {})
    with pytest.raises(setup.SetupFailure,match='Chromium') as failed:
        setup.prepare(home)
    assert failed.value.code=='browser_missing' and not installed(home)


@pytest.mark.parametrize('separator',[b'\n',b'\r\n'])
def test_repeated_log_trimming_keeps_byte_limit_and_line_endings(home,monkeypatch,separator):
    log=home/'setup.log'
    monkeypatch.setattr(setup,'LOG_LIMIT',128)
    log.write_bytes(('старый вывод'.encode('utf-8')+separator)*100+b'ERROR newest'+separator)
    setup.trim_log(log)
    first=log.read_bytes()
    assert len(first)==128 and first.endswith(b'ERROR newest'+separator)
    assert b'\r\r\n' not in first
    setup.trim_log(log)
    assert log.read_bytes()==first
    assert not list(home.glob('.setup.log.*.tmp'))


def test_failed_log_replacement_preserves_the_previous_log(home,monkeypatch):
    log=home/'setup.log'
    original=b'previous log\r\n'*100
    log.write_bytes(original)
    monkeypatch.setattr(setup,'LOG_LIMIT',128)
    def locked(*args):raise PermissionError('Log is locked')
    monkeypatch.setattr(type(log),'replace',locked)
    setup.trim_log(log)
    assert log.read_bytes()==original
    assert not list(home.glob('.setup.log.*.tmp'))


def probe_packages(home,python_version=None,driver_version=None):
    libraries=home/'libraries'
    for name in ('pyee','greenlet','playwright'):
        package=libraries/name; package.mkdir(parents=True,exist_ok=True)
        (package/'__init__.py').write_text('')
    (libraries/'playwright/_repo_version.py').write_text('version='+repr(python_version or setup.VERSION))
    driver=libraries/'playwright/driver/package'
    driver.mkdir(parents=True)
    (driver/'package.json').write_text(json.dumps({'version':driver_version or setup.VERSION}))
    (libraries/'playwright/sync_api.py').write_text('''
from types import SimpleNamespace
class sync_playwright:
    def __enter__(self):return SimpleNamespace(chromium=SimpleNamespace(executable_path='/cached/chrome'))
    def __exit__(self,*args):pass
''')
    return libraries


@pytest.mark.parametrize('python_version,driver_version,valid',[
    (None,None,True),('0.0.0',None,False),(None,'0.0.0',False)])
def test_probe_checks_python_and_driver_versions(tmp_path,python_version,driver_version,valid):
    libraries=probe_packages(tmp_path,python_version,driver_version)
    result=subprocess.run([sys.executable,'-c',setup.LIBRARY_PROBE,str(libraries),setup.VERSION],
                          capture_output=True,text=True,timeout=10)
    assert (result.returncode==0)==valid
    if valid:
        assert json.loads(result.stdout)['version']==setup.VERSION


def test_probe_rejects_dependency_from_another_environment(tmp_path):
    libraries=probe_packages(tmp_path)
    # Leave a valid global-looking pyee on PYTHONPATH, but remove the optional one.
    (libraries/'pyee/__init__.py').unlink(); (libraries/'pyee').rmdir()
    elsewhere=tmp_path/'global'; (elsewhere/'pyee').mkdir(parents=True)
    (elsewhere/'pyee/__init__.py').write_text('')
    env=dict(os.environ,PYTHONPATH=str(elsewhere))
    result=subprocess.run([sys.executable,'-c',setup.LIBRARY_PROBE,str(libraries),setup.VERSION],
                          capture_output=True,text=True,timeout=10,env=env)
    assert result.returncode!=0 and 'another environment: pyee' in result.stderr
