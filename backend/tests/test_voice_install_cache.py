"""Scott Voice retries retain completed packages in its own bounded pip cache."""
import json
import os
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
import installation_space
import scott_voice_install as setup
import setup_cache
import torch_download
import voice_asset_update
import voice_shared_runtime

pytestmark = pytest.mark.unit


@pytest.fixture
def installer(tmp_path, monkeypatch):
    # Exercise the Windows installer flow on both CI platforms, without changing
    # global os.name/Path semantics or qualifying Linux TTS.
    monkeypatch.setattr(setup, 'os', SimpleNamespace(**(vars(os) | {'name': 'nt'})))
    monkeypatch.setattr(setup, 'preflight_nvidia', lambda: None)
    monkeypatch.setattr(setup, 'asset_sources', lambda root: {})
    monkeypatch.setattr(voice_asset_update, 'sync_assets', lambda *a, **kw: None)
    monkeypatch.setattr(voice_asset_update, 'manifest', lambda *a: {})
    monkeypatch.setattr(voice_shared_runtime, 'candidate', lambda *a: None)
    monkeypatch.setattr(voice_shared_runtime, 'configure', lambda *a, **kw: False)
    monkeypatch.setattr(torch_download, 'selected', lambda *a: None)
    monkeypatch.setattr(installation_space, 'require_space', lambda *a: None)
    monkeypatch.setattr(setup, 'check', lambda *a, **kw: {'available': True, 'error': ''})
    home = tmp_path/'voice runtime'
    home.mkdir()
    setup.write_json(home/'scott-install.json', dict(version=1,model=setup.MODEL,revision=setup.REVISION,ready=False))
    executable=setup.python_path(home)
    executable.parent.mkdir(parents=True)
    executable.write_text('synthetic executable')
    (executable.parent.parent/'pyvenv.cfg').write_text('include-system-site-packages = false')
    root=tmp_path/'app'
    root.mkdir()
    global_cache=tmp_path/'global-cache'
    global_cache.mkdir()
    sentinel=global_cache/'keep.whl'
    sentinel.write_bytes(b'foreign cache')
    monkeypatch.setenv('PIP_CACHE_DIR', str(global_cache))

    class Runner:
        def __init__(self):
            self.cancelled=threading.Event()
            self.calls=[]
            self.framework=False
            self.libraries=False
            self.fail=None
            self.cache_paths=[]
            self.payloads=[]
        def step(self,*args): pass
        def __call__(self,command,**kw):
            self.calls.append((list(command),dict(kw)))
            if '-c' in command:
                if 'import importlib.metadata' in command[-1]:
                    ready=self.libraries if 'qwen_tts' in command[-1] else self.framework
                    if not ready: raise subprocess.CalledProcessError(1,command)
                return SimpleNamespace(stdout='(3, 13):8',returncode=0)
            if '--help' in command:
                return SimpleNamespace(stdout='--resume-retries',returncode=0)
            if '-m' in command and 'pip' in command and 'install' in command:
                phase='framework' if '--index-url' in command else 'libraries'
                if '--cache-dir' in command:
                    cache=Path(command[command.index('--cache-dir')+1])
                    self.cache_paths.append(cache)
                    body=cache/'http-v2'/phase/'payload.body'
                    body.parent.mkdir(parents=True,exist_ok=True)
                    body.write_bytes(phase.encode())
                    self.payloads.append(body)
                if self.fail==phase: raise subprocess.CalledProcessError(19,command)
                if phase=='framework': self.framework=True
                else: self.libraries=True
            if 'check' in command and self.fail=='check':
                raise subprocess.CalledProcessError(23,command)
            if '--download-model' in command and self.fail=='model':
                raise subprocess.CalledProcessError(29,command)
            return SimpleNamespace(stdout='',returncode=0)
    runner=Runner()
    def run():
        result=setup.install(home, executable, root, runner=runner)
        assert sentinel.read_bytes()==b'foreign cache'
        return result
    return SimpleNamespace(home=home,runner=runner,run=run,sentinel=sentinel)


@pytest.mark.parametrize('failure',['framework','libraries','check'])
def test_retry_keeps_completed_packages_until_libraries_pass(installer,failure):
    it=installer
    it.runner.fail=failure
    with pytest.raises(subprocess.CalledProcessError): it.run()
    cache=it.home/'download-cache/pip'
    assert it.runner.cache_paths and set(it.runner.cache_paths)=={cache}
    assert all(p.is_file() for p in it.runner.payloads)
    assert not json.loads((it.home/'scott-install.json').read_text())['ready']
    assert not (it.home/'installation.lock').exists()
    it.runner.fail=None
    assert it.run()['available']
    assert all(not p.exists() for p in it.runner.payloads)
    assert json.loads((cache/setup_cache.MARKER).read_text())==setup_cache.IDENTITY
    for command,kw in it.runner.calls:
        if 'install' in command and '--help' not in command:
            assert '--no-cache-dir' not in command
            assert '--resume-retries' in command
            assert kw['timeout'] in (3600,1800)
            assert 'PIP_CACHE_DIR' not in kw['env']
    assert it.sentinel.read_bytes()==b'foreign cache'


def test_model_failure_keeps_libraries_without_extra_pip_cache(installer):
    it=installer
    it.runner.fail='model'
    with pytest.raises(subprocess.CalledProcessError): it.run()
    assert it.runner.payloads and all(not p.exists() for p in it.runner.payloads)
    installs=len(it.runner.cache_paths)
    it.runner.fail=None
    assert it.run()['available']
    assert len(it.runner.cache_paths)==installs


@pytest.mark.parametrize('problem',['foreign','permission','linked'])
def test_unavailable_cache_preserves_foreign_data_and_installs_without_cache(installer,monkeypatch,problem,tmp_path):
    it=installer
    cache=it.home/'download-cache/pip'
    foreign=tmp_path/'foreign'
    foreign.mkdir()
    keep=foreign/'keep'
    keep.write_bytes(b'preserved')
    if problem=='foreign':
        cache.mkdir(parents=True)
        (cache/'unowned').write_bytes(b'preserved')
    elif problem=='linked':
        cache.parent.mkdir(parents=True)
        try: cache.symlink_to(foreign,target_is_directory=True)
        except OSError: pytest.skip('Symlink privilege unavailable')
    else:
        def denied(*a): raise PermissionError('controlled cache denial')
        monkeypatch.setattr(setup_cache,'prepare',denied)
    assert it.run()['available']
    assert not it.runner.cache_paths
    assert keep.read_bytes()==b'preserved'
    if problem=='foreign': assert (cache/'unowned').read_bytes()==b'preserved'
    for command,_ in it.runner.calls:
        if 'install' in command and '--help' not in command:
            assert '--no-cache-dir' in command and '--cache-dir' not in command


def test_cache_is_bounded_on_failed_pip_without_changing_error(installer,monkeypatch):
    it=installer
    monkeypatch.setattr(setup_cache,'LIMIT',1)
    it.runner.fail='libraries'
    with pytest.raises(subprocess.CalledProcessError) as caught: it.run()
    assert caught.value.returncode==19
    assert it.runner.payloads and all(not p.exists() for p in it.runner.payloads)
    assert it.sentinel.read_bytes()==b'foreign cache'


def test_cancelled_pip_preserves_cache_and_original_cancellation(installer):
    it=installer
    original=it.runner.__class__.__call__
    class Cancelled(RuntimeError): pass
    def cancel(owner,command,**kw):
        result=original(owner,command,**kw)
        if 'install' in command and '--help' not in command:
            owner.cancelled.set()
            raise Cancelled('controlled cancellation')
        return result
    it.runner.__class__.__call__=cancel
    try:
        with pytest.raises(Cancelled,match='controlled cancellation'): it.run()
        assert it.runner.payloads and all(p.exists() for p in it.runner.payloads)
        assert not (it.home/'installation.lock').exists()
    finally:
        it.runner.__class__.__call__=original
