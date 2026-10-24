"""Upgrade an owned legacy voice venv without leaving web-UI dependency conflicts."""
import csv
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
import scott_voice_install as setup
from test_voice_install_cache import installer

pytestmark = pytest.mark.unit

def package(home, name, *, record=True, extra=()):
    venv = setup.python_path(home).parent.parent
    site = venv/'Lib/site-packages'
    info = site/(name.replace('-', '_')+'-1.0.dist-info')
    info.mkdir(parents=True)
    (info/'METADATA').write_text(f'Metadata-Version: 2.1\nName: {name}\nVersion: 1.0\n')
    if record:
        with (info/'RECORD').open('w', newline='') as stream:
            csv.writer(stream).writerows((item, '', '') for item in (
                info.relative_to(site).as_posix()+'/METADATA',
                info.relative_to(site).as_posix()+'/RECORD', *extra))
    return info

def legacy(it):
    return [package(it.home, name) for name in ('gradio', 'gradio-client')]

def test_upgrade_removes_retired_web_ui_before_strict_pip_check(installer, monkeypatch):
    it = installer
    infos = legacy(it)
    it.runner.framework = it.runner.libraries = True
    original = it.runner.__class__.__call__
    def run(owner, command, **kwargs):
        if command[1:4] == ['-m', 'pip', 'uninstall']:
            assert command[4:] == ['--yes', 'gradio', 'gradio-client']
            assert command[0] == str(setup.python_path(it.home))
            for info in infos:
                info.rename(info.with_suffix('.retired'))
            owner.calls.append((list(command), dict(kwargs)))
            return SimpleNamespace(returncode=0)
        if command[1:] == ['-m', 'pip', 'check'] and any(info.exists() for info in infos):
            raise subprocess.CalledProcessError(1, command, output='gradio requires huggingface-hub<2.0')
        return original(owner, command, **kwargs)
    monkeypatch.setattr(it.runner.__class__, '__call__', run)
    assert it.run()['available']
    assert not any('install' in cmd and '--help' not in cmd for cmd, _ in it.runner.calls)
    assert any(cmd[1:] == ['-m', 'pip', 'check'] for cmd, _ in it.runner.calls)

def test_cleanup_keeps_unrelated_packages_and_model_files(installer):
    it = installer
    legacy(it)
    other = package(it.home, 'unrelated')
    weight = it.home/'experiments/voice_design/models/base/keep.bin'
    weight.parent.mkdir(parents=True)
    weight.write_bytes(b'unchanged model')
    calls = []
    setup._retire_web_packages(it.home, lambda cmd, **kw: calls.append((cmd, kw)), {})
    assert calls[0][0] == [str(setup.python_path(it.home)), '-m', 'pip', 'uninstall', '--yes', 'gradio', 'gradio-client']
    assert calls[0][1]['check'] and calls[0][1]['timeout'] == 120
    assert other.is_dir() and weight.read_bytes() == b'unchanged model'

def test_fresh_environment_needs_no_cleanup(installer):
    setup._retire_web_packages(installer.home, lambda *a, **kw: pytest.fail('No web packages'), {})

@pytest.mark.parametrize('problem', ['record-missing', 'record-escape', 'global-site', 'site-escape'])
def test_cleanup_rejects_unverified_or_external_package_files(installer, problem):
    it = installer
    package(it.home, 'gradio', record=problem != 'record-missing',
            extra=('../../../../../foreign.txt',) if problem == 'record-escape' else ())
    if problem == 'global-site':
        (setup.python_path(it.home).parent.parent/'pyvenv.cfg').write_text('include-system-site-packages = true')
    if problem == 'site-escape':
        # RECORD path normalization must reject absolute paths as well as .. traversal.
        info = next((setup.python_path(it.home).parent.parent/'Lib/site-packages').glob('*.dist-info'))
        with (info/'RECORD').open('a', newline='') as stream:
            csv.writer(stream).writerow((str(it.home.parent/'foreign.txt'), '', ''))
    with pytest.raises(ValueError):
        setup._retire_web_packages(it.home, lambda *a, **kw: pytest.fail('Must not uninstall'), {})

def test_cleanup_propagates_uninstall_failure(installer):
    package(installer.home, 'gradio')
    def fail(command, **kwargs):
        raise subprocess.CalledProcessError(23, command)
    with pytest.raises(subprocess.CalledProcessError) as caught:
        setup._retire_web_packages(installer.home, fail, {})
    assert caught.value.returncode == 23

def test_conflicts_outside_retired_web_ui_still_fail_strict_check(installer):
    installer.runner.framework = installer.runner.libraries = True
    installer.runner.fail = 'check'
    with pytest.raises(subprocess.CalledProcessError) as caught:
        installer.run()
    assert caught.value.returncode == 23

def test_legacy_hub_web_bridge_does_not_require_removed_gradio_client(installer, monkeypatch):
    it = installer
    infos = legacy(it) + [package(it.home, 'hf-gradio')]
    it.runner.framework = it.runner.libraries = True
    original = it.runner.__class__.__call__
    def run(owner, command, **kwargs):
        if command[1:4] == ['-m', 'pip', 'uninstall']:
            for name in command[5:]:
                info = next(info for info in infos if info.name.startswith(name.replace('-', '_')+'-'))
                info.rename(info.with_suffix('.retired'))
            owner.calls.append((list(command), dict(kwargs)))
            return SimpleNamespace(returncode=0)
        if command[1:] == ['-m', 'pip', 'check'] and any(info.exists() for info in infos):
            raise subprocess.CalledProcessError(1, command, output='hf-gradio requires gradio-client')
        return original(owner, command, **kwargs)
    monkeypatch.setattr(it.runner.__class__, '__call__', run)
    assert it.run()['available']
    assert any(cmd[5:] == ['gradio', 'gradio-client', 'hf-gradio'] for cmd, _ in it.runner.calls)
