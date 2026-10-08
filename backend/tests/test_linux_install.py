"""Linux installer path safety and preservation, using disposable synthetic files."""
import importlib.util
import hashlib
import json
import subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('linux_installer', ROOT/'installer/linux/install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


@pytest.fixture
def package(tmp_path):
    source = tmp_path/'package'
    (source/'launcher').mkdir(parents=True)
    (source/'launcher/ScottAIQt').write_bytes(b'synthetic executable')
    (source/'backend').mkdir()
    (source/'backend/main.py').write_text('# synthetic backend\n')
    (source/'VERSION.json').write_text('{"version":"2.0.0"}')
    core = {}
    for name in ('bin/python3.13', 'lib/python3.13/os.py', 'lib/python3.13/venv/__init__.py'):
        file = source/'python-runtime'/name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b'synthetic bundled python')
        core[name] = hashlib.sha256(file.read_bytes()).hexdigest()
    (source/'python-runtime/.scott-python.json').write_text(json.dumps(
        {'version':'3.13.16', 'sha256':'synthetic-archive', 'core':core}))
    return source


def test_rejects_unowned_nonempty_destination(tmp_path, package):
    target = tmp_path/'other'
    target.mkdir()
    (target/'personal.txt').write_text('preserve')
    with pytest.raises(ValueError, match='Непустая'):
        installer.safe_prefix(target, package)
    assert (target/'personal.txt').read_text() == 'preserve'


def test_rejects_destination_inside_package(package):
    with pytest.raises(ValueError):
        installer.safe_prefix(package/'installed', package)


def test_rejects_parent_of_package(package):
    with pytest.raises(ValueError):
        installer.safe_prefix(package.parent, package)


@pytest.mark.parametrize('name', ['../personal.txt', '/personal.txt'])
def test_rejects_manifest_escape(tmp_path, name):
    with pytest.raises(ValueError):
        installer.target_file(tmp_path, name)


def test_refuses_personal_data_in_package(package):
    (package/'backend/data').mkdir()
    (package/'backend/data/history.json').write_text('{}')
    with pytest.raises(ValueError, match='данные'):
        installer.payload_files(package)


def test_upgrade_and_uninstall_preserve_data(tmp_path, package, monkeypatch):
    target = tmp_path/'Scott AI'
    # The real venv is checked on Linux CI; keep this test independent of the host.
    def environment(*args, **kwargs):
        runtime = target/'runtime'
        (runtime/'bin').mkdir(parents=True, exist_ok=True)
        (runtime/'bin/python').write_text('synthetic')
        (runtime/'pyvenv.cfg').write_text('synthetic')
    monkeypatch.setattr(installer.subprocess, 'run', environment)
    installer.install(target, package, shortcut=False)
    data = target/'backend/data/history.json'
    data.parent.mkdir()
    data.write_bytes(b'{"synthetic":true}')
    (target/'.env').write_text('SYNTHETIC=1\n')
    (package/'backend/main.py').write_text('# newer synthetic backend\n')
    installer.install(target, package, shortcut=False)
    assert (target/'backend/main.py').read_text() == '# newer synthetic backend\n'
    installer.uninstall(target)
    assert data.read_bytes() == b'{"synthetic":true}'
    assert (target/'.env').read_text() == 'SYNTHETIC=1\n'
    assert not (target/'launcher/ScottAIQt').exists()
    installer.install(target, package, shortcut=False)
    assert data.read_bytes() == b'{"synthetic":true}'


def test_malicious_marker_cannot_remove_data(tmp_path):
    target = tmp_path/'owned'
    (target/'backend/data').mkdir(parents=True)
    data = target/'backend/data/history.json'
    data.write_text('preserve')
    (target/installer.MARKER).write_text(json.dumps({'files':['backend/data/history.json']}))
    with pytest.raises(ValueError, match='данные'):
        installer.uninstall(target)
    assert data.read_text() == 'preserve'


def test_retry_repairs_partial_environment(tmp_path, package, monkeypatch):
    target = tmp_path/'retry'
    calls = []
    def environment(*args, **kwargs):
        runtime = target/'runtime'
        runtime.mkdir(exist_ok=True)
        calls.append(True)
        if len(calls) == 1:
            raise subprocess.CalledProcessError(1, ['synthetic-venv'])
        (runtime/'bin').mkdir()
        (runtime/'bin/python').write_text('synthetic')
        (runtime/'pyvenv.cfg').write_text('synthetic')
    monkeypatch.setattr(installer.subprocess, 'run', environment)
    with pytest.raises(subprocess.CalledProcessError):
        installer.install(target, package, shortcut=False)
    installer.install(target, package, shortcut=False)
    assert len(calls) == 2
    assert (target/'runtime/bin/python').is_file()


@pytest.mark.parametrize('version', [(3, 10, 0)])
def test_rejects_unsupported_python_before_install(version, monkeypatch):
    monkeypatch.setattr(installer.sys, 'platform', 'linux')
    monkeypatch.setattr(installer.sys, 'version_info', version)
    monkeypatch.setattr(installer.sys, 'argv', ['install.py'])
    monkeypatch.setattr(installer, 'install', lambda *args, **kwargs: pytest.fail('Installation must not start'))
    with pytest.raises(SystemExit) as error:
        installer.main()
    assert error.value.code == 2


def test_newer_host_python_does_not_restrict_bundled_backend(monkeypatch):
    monkeypatch.setattr(installer.sys, 'platform', 'linux')
    monkeypatch.setattr(installer.sys, 'version_info', (3, 14, 0))
    monkeypatch.setattr(installer.sys, 'argv', ['install.py'])
    calls = []
    monkeypatch.setattr(installer, 'install', lambda *a, **kw: calls.append(True))
    assert installer.main() == 0
    assert calls == [True]


def test_corrupt_python_rejected_before_copy(tmp_path, package):
    (package/'python-runtime/bin/python3.13').write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='повреждены'):
        installer.install(tmp_path/'installed', package, shortcut=False)
    assert not (tmp_path/'installed').exists()


def test_foreign_runtime_is_not_claimed(tmp_path, package):
    target = tmp_path/'installed'
    (target/'runtime').mkdir(parents=True)
    (target/'runtime/pyvenv.cfg').write_text('foreign environment')
    metadata = {'files':[], 'runtime_owned':False}
    (target/installer.MARKER).write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match='не принадлежит'):
        installer.install(target, package, shortcut=False)
    assert json.loads((target/installer.MARKER).read_text()) == metadata
    assert (target/'runtime/pyvenv.cfg').read_text() == 'foreign environment'


def test_failed_legacy_upgrade_restores_environment(tmp_path, package, monkeypatch):
    target = tmp_path/'installed'
    (target/'runtime/bin').mkdir(parents=True)
    (target/'runtime/bin/python').write_bytes(b'old interpreter')
    (target/'runtime/pyvenv.cfg').write_text('old environment')
    (target/installer.MARKER).write_text(json.dumps({'files':[], 'runtime_owned':True}))
    def fail(*args, **kwargs):
        (target/'runtime').mkdir()
        (target/'runtime/partial').write_bytes(b'partial')
        raise subprocess.CalledProcessError(1, ['synthetic-venv'])
    monkeypatch.setattr(installer.subprocess, 'run', fail)
    with pytest.raises(subprocess.CalledProcessError):
        installer.install(target, package, shortcut=False)
    assert (target/'runtime/bin/python').read_bytes() == b'old interpreter'
    assert not (target/'runtime/partial').exists()
    assert not list(target.glob('.runtime-before-*'))


def test_python_resource_data_is_allowed(package):
    file = package/'python-runtime/lib/python3.13/vendor/data/resource.txt'
    file.parent.mkdir(parents=True)
    file.write_text('synthetic library resource')
    assert file in installer.payload_files(package)
