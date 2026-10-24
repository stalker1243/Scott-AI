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

def test_runner_retains_failure_output_and_masks_log(tmp_path, monkeypatch):
    monkeypatch.setenv('SCOTT_LOG_DIR', str(tmp_path/'logs'))
    monkeypatch.setenv('FIXTURE_API_KEY', 'opaque-fixture-credential')
    runner = runtime.CancellableRunner(None)
    with pytest.raises(subprocess.CalledProcessError) as caught:
        runner([sys.executable, '-c', 'import sys; print("network failed opaque-fixture-credential",file=sys.stderr); sys.exit(1)'], timeout=5)
    assert 'network failed' in caught.value.stderr
    assert 'opaque-fixture-credential' not in caught.value.stderr
    log = (tmp_path/'logs/scott-voice-install.log').read_text(encoding='utf-8')
    assert 'network failed' in log and 'opaque-fixture-credential' not in log

def test_runner_times_out_silent_process_and_keeps_stdout():
    runner = runtime.CancellableRunner(None)
    with pytest.raises(subprocess.TimeoutExpired):
        runner([sys.executable, '-c', 'import time; time.sleep(30)'], timeout=.25)
    result = runner([sys.executable, '-c', 'import sys; print("probe"); print("warning",file=sys.stderr)'], capture_output=True, timeout=5)
    assert result.stdout.strip() == 'probe' and result.stderr.strip() == 'warning'


def test_runner_forwards_model_progress_on_its_own_thread():
    updates = []
    owner = threading.get_ident()
    runner = runtime.CancellableRunner(lambda *event: updates.append((threading.get_ident(), event)))
    runner.step('model', 'Downloading', .6)
    event = json.dumps(dict(type='progress', stage='model', message='model.bin', fraction=.72))
    bad = json.dumps(dict(type='progress', stage='model', message='bad', fraction=float('nan')))
    runner([sys.executable, '-c', f'print({event!r}); print({bad!r})'], timeout=5)
    assert any(e[1] == ('model', 'model.bin', .72) for e in updates)
    assert all(e[0] == owner and e[1][1] != 'bad' for e in updates)


def test_runner_retains_structured_error_without_capture_output():
    event = json.dumps(dict(type='error', code='download_access', message='denied'))
    runner = runtime.CancellableRunner(None)
    with pytest.raises(subprocess.CalledProcessError) as caught:
        runner([sys.executable, '-c', f'import sys; print({event!r}); sys.exit(1)'], timeout=5)
    from voice_install_errors import child_failure
    assert child_failure(caught.value).code == 'download_access'

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
@pytest.mark.parametrize('old_sdk',[False,True])
def test_cli_check_with_open_cancel_pipe(tmp_path, monkeypatch,old_sdk):
    import scott_voice_install as setup
    import scott_voice_engine as engine
    import os
    # A real venv launcher with synthetic modules avoids Torch/model imports.
    home = tmp_path/'home'
    config = engine.config_at(home)
    subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(config.python.parent.parent)], check=True)
    modules = config.python.parent.parent/'Lib/site-packages'
    modules.mkdir(parents=True, exist_ok=True)
    (modules/'torch.py').write_text('class cuda:\n @staticmethod\n def is_available(): return True\n')
    if old_sdk:
        (modules/'torch.py').write_text('raise RuntimeError("An outdated SDK must not be imported before repair")\n')
    for name in ('qwen_tts', 'soundfile', 'scipy'):
        (modules/(name+'.py')).write_text('')
    from scott_voice_sdk import VERSIONS
    for name,version in VERSIONS.items():
        if old_sdk and name=='qwen-tts':version='0.1.1'
        metadata=modules/(name.replace('-','_')+'-'+version+'.dist-info')
        metadata.mkdir()
        (metadata/'METADATA').write_text('Name: '+name+'\nVersion: '+version+'\n')
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
        assert process.returncode == (1 if old_sdk else 0)
        result=json.loads(process.stdout.read())
        assert result['available'] is not old_sdk
        if old_sdk:assert result['error']=='runtime_update_required'
    finally:
        if process.poll() is None:
            owner = psutil.Process(process.pid)
            from scott_voice_process import stop_process_tree
            stop_process_tree(process, owner)
        process.stdin.close(); process.stdout.close()
