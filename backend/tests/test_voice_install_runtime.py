"""Private Python package and owned child cancellation; all files are synthetic."""
import hashlib
import json
import sys
import threading
import time
import subprocess
import zipfile
from pathlib import Path
import psutil
import pytest
import voice_install_runtime as runtime

pytestmark = pytest.mark.unit

@pytest.fixture
def package(tmp_path, monkeypatch):
    archive = tmp_path/'fixture.zip'
    with zipfile.ZipFile(archive, 'w') as bundle:
        for name in ('tools/python.exe', 'tools/python313.dll', 'tools/Lib/venv/__init__.py'):
            bundle.writestr(name, 'synthetic binary')
        bundle.writestr('outside.txt', 'metadata is not extracted')
    monkeypatch.setattr(runtime, 'PYTHON_SHA256', runtime.digest(archive))
    return archive

def test_private_package_hash_and_reuse(tmp_path, package):
    home = tmp_path/'home'
    python = runtime.prepare_python(home, package=package)
    assert python.is_file()
    assert not (home/'python/outside.txt').exists()
    assert runtime.prepare_python(home, package=package) == python
    python.write_bytes(b'broken')
    assert runtime.prepare_python(home, package=package).read_bytes() == b'synthetic binary'

def test_bad_package_never_extracts(tmp_path, package):
    package.write_bytes(b'corrupted')
    home = tmp_path/'home'
    with pytest.raises(ValueError, match='сумма'):
        runtime.prepare_python(home, package=package)
    assert not home.exists()

@pytest.mark.parametrize('name', ['tools/../../escaped', 'tools/a/../../../escaped', 'tools/back\\slash', 'tools/python.exe:alternate'])
def test_archive_paths_rejected_before_writes(tmp_path, package, monkeypatch, name):
    with zipfile.ZipFile(package, 'a') as bundle:
        entry = zipfile.ZipInfo('fixture')
        entry.filename = name  # ZipInfo normally normalizes Windows separators.
        bundle.writestr(entry, 'escape')
    monkeypatch.setattr(runtime, 'PYTHON_SHA256', runtime.digest(package))
    with pytest.raises(ValueError, match='путь'):
        runtime.prepare_python(tmp_path/'home', package=package)
    assert not (tmp_path/'home/python').exists()

def test_cancelled_bootstrap_does_not_write(tmp_path, package):
    event = threading.Event(); event.set()
    with pytest.raises(runtime.InstallationCancelled):
        runtime.prepare_python(tmp_path/'home', package=package, cancelled=event)
    assert not (tmp_path/'home').exists()

def test_cancel_runner_terminates_owned_grandchild(tmp_path):
    pid_file = tmp_path/'child.json'
    script = ('import subprocess,sys,time,json; '
        'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); '
        f'open({str(pid_file)!r},"w").write(json.dumps(p.pid)); time.sleep(60)')
    runner = runtime.CancellableRunner(None)
    errors = []
    def run():
        try:
            runner([sys.executable, '-c', script], check=True)
        except runtime.InstallationCancelled:
            errors.append('cancelled')
    thread = threading.Thread(target=run); thread.start()
    deadline = time.monotonic()+5
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(.02)
    assert pid_file.exists()
    child = psutil.Process(json.loads(pid_file.read_text()))
    runner.cancelled.set(); thread.join(timeout=10)
    assert not thread.is_alive() and errors == ['cancelled']
    assert not child.is_running()

def test_malformed_parent_identity_cancels(monkeypatch):
    monkeypatch.setenv('SCOTT_VOICE_INSTALL_OWNER', '123')
    monkeypatch.setenv('SCOTT_VOICE_INSTALL_OWNER_CREATED', 'invalid')
    runner = runtime.CancellableRunner(None)
    runner.watch_parent()
    assert runner.cancelled.is_set()


def test_noninteractive_child_does_not_consume_cancel_pipe():
    script = (f'import sys; sys.path.insert(0,{str(Path(runtime.__file__).parent)!r}); '
        'from voice_install_runtime import CancellableRunner; '
        'r=CancellableRunner(None)([sys.executable,"-c","import sys; assert sys.stdin.read()==\\\"\\\"; print(\\\"ready\\\")"],'
        'capture_output=True,text=True,timeout=2); print(r.stdout,flush=True)')
    process = subprocess.Popen([sys.executable, '-c', script], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        process.wait(timeout=8)
        assert process.returncode == 0 and process.stdout.read().strip() == 'ready'
    finally:
        if process.poll() is None:
            from scott_voice_process import stop_process_tree
            stop_process_tree(process, psutil.Process(process.pid))
        process.stdin.close(); process.stdout.close()


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows pipe inheritance regression')
def test_cli_check_with_open_cancel_pipe(tmp_path, monkeypatch):
    import scott_voice_install as setup
    import scott_voice_engine as engine
    import os
    # A real venv launcher with synthetic modules avoids Torch/model imports.
    home = tmp_path/'home'
    config = engine.config_at(home)
    subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(config.python.parent.parent)], check=True)
    modules = tmp_path/'modules'; modules.mkdir()
    (modules/'torch.py').write_text('class cuda:\n @staticmethod\n def is_available(): return True\n')
    for name in ('qwen_tts', 'soundfile', 'scipy'):
        (modules/(name+'.py')).write_text('')
    for path in (config.worker, config.profiles_json, *[config.model_dir/n for n in setup.MODEL_FILES]):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text('{}')
    hashes = {n: setup.checksum(config.model_dir/n) for n in setup.MODEL_FILES}
    setup.write_json(config.model_dir/'scott-model.json', dict(model='fixture',revision='fixture',files=list(hashes),sha256=hashes))
    config.reference_json.parent.mkdir(parents=True)
    reference = config.reference_json.with_name('scott-reference.wav'); reference.write_bytes(b'synthetic reference')
    setup.write_json(config.reference_json, {'sha256':setup.checksum(reference)})
    env = dict(os.environ, PYTHONPATH=str(modules), PYTHONUTF8='1')
    env.pop('SCOTT_VOICE_INSTALL_OWNER', None)
    process = subprocess.Popen([sys.executable, setup.__file__, '--check', '--deep', '--json', '--home', str(home)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf-8', env=env,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        # Keep cancellation stdin open until completion, like the live backend.
        process.wait(timeout=10)
        assert process.returncode == 0
        assert json.loads(process.stdout.read())['available'] is True
    finally:
        if process.poll() is None:
            owner = psutil.Process(process.pid)
            from scott_voice_process import stop_process_tree
            stop_process_tree(process, owner)
        process.stdin.close(); process.stdout.close()
