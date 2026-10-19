"""Linux installer path safety and preservation, using disposable synthetic files."""
import importlib.util
import hashlib
import json
import subprocess
import os
import shutil
import sys
from pathlib import Path
import pytest
import socket

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('linux_installer', ROOT/'installer/linux/install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


@pytest.mark.skipif(os.name=='nt', reason='Linux shell and Unix socket')
@pytest.mark.parametrize('plugin,live_socket,display,override,expected', [
    (True,True,'relative','','wayland;xcb'), (True,True,'absolute','','wayland;xcb'),
    (False,True,'relative','','xcb'), (True,False,'relative','','xcb'),
    (True,True,'relative','offscreen','offscreen'), (True,True,'relative','xcb','xcb'),
    (True,True,'invalid-runtime','','xcb')])
def test_run_selects_packaged_platform_without_running_backend(tmp_path,plugin,live_socket,display,override,expected):
    app=tmp_path/'app'
    for directory in ('runtime/bin','launcher','plugins/platforms'):
        (app/directory).mkdir(parents=True)
    python=app/'runtime/bin/python'; python.write_text('# synthetic placeholder'); python.chmod(0o755)
    (app/'python-environment.sh').write_text('# synthetic empty environment\n')
    launcher=app/'launcher/ScottAIQt'
    launcher.write_text('#!/bin/bash\nprintf "%s\\n" "$QT_QPA_PLATFORM" "$@" "$PWD"\n'); launcher.chmod(0o755)
    if plugin:
        (app/'plugins/platforms/libqwayland.so').write_bytes(b'fixture plugin never loaded')
    script=app/'run.sh'; shutil.copy2(ROOT/'installer/linux/run.sh',script)
    runtime=tmp_path/'session'; runtime.mkdir()
    path=runtime/'wayland-0'
    with socket.socket(socket.AF_UNIX) as session:
        if live_socket: session.bind(str(path))
        else: path.write_bytes(b'stale non-socket')
        env=dict(os.environ, XDG_RUNTIME_DIR=str(runtime),WAYLAND_DISPLAY=str(path) if display=='absolute' else 'wayland-0')
        if display=='invalid-runtime': env['XDG_RUNTIME_DIR']='relative/session'
        if override: env['QT_QPA_PLATFORM']=override
        else: env.pop('QT_QPA_PLATFORM',None)
        result=subprocess.run(['/bin/bash',str(script),'--smoke-chat'],env=env,cwd=tmp_path,capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    assert result.stdout.splitlines()==[expected,'--start-backend','--smoke-chat',str(tmp_path)]


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
        {'version':'3.13.16', 'sha256':'a'*64, 'core':core}))
    return source


def test_rejects_unowned_nonempty_destination(tmp_path, package):
    target = tmp_path/'other'
    target.mkdir()
    (target/'personal.txt').write_text('preserve')
    with pytest.raises(ValueError, match='Непустая'):
        installer.safe_prefix(target, package)
    assert (target/'personal.txt').read_text() == 'preserve'


def test_default_prefix_honors_xdg_without_creating_files(tmp_path, monkeypatch):
    home = tmp_path/'home'
    custom = tmp_path/'custom data'
    monkeypatch.setattr(Path, 'home', lambda: home)
    monkeypatch.setenv('XDG_DATA_HOME', str(custom))
    assert installer.default_prefix() == custom/'ScottAI'
    assert not custom.exists() and not home.exists()


@pytest.mark.parametrize('value', ['', 'relative', '~/relative'])
def test_default_prefix_ignores_invalid_xdg(value, tmp_path, monkeypatch):
    monkeypatch.setattr(Path,'home',lambda: tmp_path)
    monkeypatch.setenv('XDG_DATA_HOME',value)
    assert installer.default_prefix() == tmp_path/'.local/share/ScottAI'


def test_default_prefix_keeps_existing_legacy_install_when_xdg_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setenv('XDG_DATA_HOME',str(tmp_path/'custom'))
    legacy=tmp_path/'.local/share/ScottAI'
    legacy.mkdir(parents=True)
    (legacy/installer.MARKER).write_text('{}')
    assert installer.default_prefix() == legacy


def test_shortcut_path_roundtrip_and_uninstall_after_xdg_change(tmp_path, monkeypatch):
    prefix = tmp_path/'Scott %f $HOME `literal` = space'
    prefix.mkdir()
    custom = tmp_path/'xdg'
    monkeypatch.setenv('XDG_DATA_HOME', str(custom))
    shortcut=installer.desktop_entry(prefix)
    assert shortcut == custom/'applications/com.scottai.launcher.desktop'
    content=shortcut.read_text(encoding='utf-8')
    assert '%%f' in content and 'Terminal=false' in content
    assert installer.owns_shortcut(shortcut,prefix)
    (prefix/installer.MARKER).write_text(json.dumps(dict(files=[],shortcut=str(shortcut))))
    monkeypatch.setenv('XDG_DATA_HOME',str(tmp_path/'another-xdg'))
    installer.uninstall(prefix)
    assert not shortcut.exists()


def test_unknown_shortcut_is_preserved_on_install_and_uninstall(tmp_path, monkeypatch):
    prefix=tmp_path/'app';prefix.mkdir()
    monkeypatch.setenv('XDG_DATA_HOME',str(tmp_path/'xdg'))
    path=tmp_path/'xdg/applications/com.scottai.launcher.desktop'
    path.parent.mkdir(parents=True)
    path.write_text('[Desktop Entry]\nName=Another application\nExec=/bin/true\n')
    before=path.read_bytes()
    with pytest.raises(ValueError,match='Ярлык'):
        installer.desktop_entry(prefix)
    (prefix/installer.MARKER).write_text(json.dumps(dict(files=[],shortcut=str(path))))
    installer.uninstall(prefix)
    assert path.read_bytes()==before


def test_published_shortcut_can_be_removed_safely(tmp_path):
    prefix=tmp_path/'app';prefix.mkdir()
    shortcut=tmp_path/'com.scottai.launcher.desktop'
    shortcut.write_text(f'[Desktop Entry]\nName=Scott AI\nExec="{prefix}/run.sh"\n')
    # Linux's old path has no backslash quoting. Windows needs the old encoder.
    if os.name == 'nt':
        quoted=str(prefix/'run.sh').replace('\\','\\\\')
        shortcut.write_text(f'[Desktop Entry]\nName=Scott AI\nExec="{quoted}"\n')
    assert installer.owns_shortcut(shortcut,prefix)


def test_linux_docs_are_installed_and_removed_without_touching_data(package,tmp_path,monkeypatch):
    (package/'docs').mkdir()
    (package/'docs/installation.md').write_text('installation documentation')
    target=tmp_path/'app'
    monkeypatch.setattr(installer,'prepare_environment',lambda *a: None)
    installer.install(target,package,shortcut=False)
    assert (target/'docs/installation.md').read_text()=='installation documentation'
    installer.uninstall(target)
    assert not (target/'docs/installation.md').exists()


@pytest.mark.parametrize('suffix',['\n','\r','\t','\x01'])
def test_control_characters_are_rejected_before_creating_installation(tmp_path,package,suffix):
    with pytest.raises(ValueError,match='управляющие'):
        installer.safe_prefix(tmp_path/('app'+suffix),package)

@pytest.mark.skipif(sys.platform != 'linux', reason='Linux executable permissions')
def test_lost_executable_permissions_are_restored_before_venv(package, tmp_path, monkeypatch):
    target = tmp_path/'installed'
    (package/'python-runtime/bin/python3.13').chmod(0o600)
    def environment(*args, **kwargs):
        assert os.access(target/'python-runtime/bin/python3.13', os.X_OK)
        assert os.access(target/'launcher/ScottAIQt', os.X_OK)
    def external(root, recorded):
        environment()
        runtime=Path(recorded)/'runtime/bin/python'
        runtime.parent.mkdir(parents=True)
        runtime.write_text('synthetic')
        return runtime
    monkeypatch.setattr(installer,'ensure_external_runtime',external)
    monkeypatch.setenv('XDG_DATA_HOME',str(tmp_path/'xdg'))
    installer.install(target, package, shortcut=False)

@pytest.mark.skipif(sys.platform != 'linux', reason='Linux shell entry point')
@pytest.mark.parametrize('shell', ['bash', 'sh'])
def test_shell_installer_recovers_nonexecutable_source_and_logs_failure(tmp_path, shell):
    source = tmp_path/'package'; (source/'python-runtime/bin').mkdir(parents=True)
    for name in ('install.sh', 'python-environment.sh'):
        shutil.copy2(ROOT/'installer/linux'/name, source/name)
    (source/'python-runtime/bin/python3.13').write_bytes(b'not executable')
    (source/'install.py').write_text('import sys; print("installer fallback reached"); sys.exit(7)')
    logs = tmp_path/'logs'
    result = subprocess.run([shell, str(source/'install.sh')], text=True, capture_output=True, timeout=15,
        env=dict(os.environ, SCOTT_LOG_DIR=str(logs)))
    assert result.returncode == 7 and 'installer fallback reached' in result.stdout
    text = (logs/'linux-install.log').read_text(encoding='utf-8')
    assert 'installer fallback reached' in text and '7' in text
    assert (logs.stat().st_mode & 0o777) == 0o700
    assert ((logs/'linux-install.log').stat().st_mode & 0o777) == 0o600


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux shell and permissions')
def test_relative_xdg_state_does_not_create_logs_in_working_directory(tmp_path):
    source=tmp_path/'package';(source/'python-runtime/bin').mkdir(parents=True)
    for name in ('install.sh','python-environment.sh'):
        shutil.copy2(ROOT/'installer/linux'/name,source/name)
    (source/'python-runtime/bin/python3.13').write_bytes(b'not executable')
    (source/'install.py').write_text('raise SystemExit(7)')
    home=tmp_path/'home'
    env=dict(os.environ,HOME=str(home),XDG_STATE_HOME='relative-state')
    env.pop('SCOTT_LOG_DIR',None)
    result=subprocess.run(['bash',str(source/'install.sh')],env=env,cwd=tmp_path,capture_output=True,text=True,timeout=15)
    assert result.returncode==7
    assert (home/'.local/state/ScottAI/logs/linux-install.log').is_file()
    assert not (tmp_path/'relative-state').exists()


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux symlink')
def test_shortcut_symlink_never_overwrites_or_deletes_its_target(tmp_path,monkeypatch):
    prefix=tmp_path/'app';prefix.mkdir()
    monkeypatch.setenv('XDG_DATA_HOME',str(tmp_path/'xdg'))
    target=tmp_path/'preserved.desktop'
    target.write_text('[Desktop Entry]\nName=Scott AI\nExec='+installer.desktop_exec(prefix)+'\n')
    shortcut=tmp_path/'xdg/applications/com.scottai.launcher.desktop'
    shortcut.parent.mkdir(parents=True)
    shortcut.symlink_to(target)
    before=target.read_bytes()
    with pytest.raises(ValueError,match='Ярлык'):
        installer.desktop_entry(prefix)
    (prefix/installer.MARKER).write_text(json.dumps(dict(files=[],shortcut=str(shortcut))))
    installer.uninstall(prefix)
    assert shortcut.is_symlink() and target.read_bytes()==before


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux shell entry point')
def test_shell_incomplete_archive_has_actionable_error(tmp_path):
    script = tmp_path/'install.sh'
    shutil.copy2(ROOT/'installer/linux/install.sh', script)
    result = subprocess.run(['sh', str(script)], text=True, capture_output=True, timeout=15,
        env=dict(os.environ, SCOTT_LOG_DIR=str(tmp_path/'logs')))
    assert result.returncode == 1 and 'python-environment.sh' in result.stdout
    assert 'распакован не полностью' in result.stdout


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux isolated interpreter')
def test_missing_stdlib_helper_is_reported_before_importing_other_code(tmp_path):
    folder=tmp_path/'incomplete/package'
    folder.mkdir(parents=True)
    shutil.copy2(ROOT/'installer/linux/install.py',folder/'install.py')
    result=subprocess.run([sys.executable,'-I',str(folder/'install.py'),'--help'],capture_output=True,text=True,timeout=15)
    assert result.returncode==1 and 'backend/platform_paths.py' in result.stderr
    assert 'не полностью' in result.stderr and 'Traceback' not in result.stderr


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


@pytest.mark.skipif(sys.platform!='linux',reason='External Linux venv pointer')
def test_upgrade_and_uninstall_preserve_data(tmp_path, package, monkeypatch):
    target = tmp_path/'Scott AI'
    # The real venv is checked on Linux CI; keep this test independent of the host.
    monkeypatch.setenv('XDG_DATA_HOME',str(tmp_path/'xdg'))
    def environment(root, recorded):
        runtime = Path(recorded)/'runtime'
        (runtime/'bin').mkdir(parents=True, exist_ok=True)
        (runtime/'bin/python').write_text('synthetic')
        (runtime/'pyvenv.cfg').write_text('synthetic')
        return runtime/'bin/python'
    monkeypatch.setattr(installer, 'ensure_external_runtime', environment)
    installer.install(target, package, shortcut=False)
    data = target/'backend/data/history.json'
    data.parent.mkdir()
    data.write_bytes(b'{"synthetic":true}')
    (target/'.env').write_text('SYNTHETIC=1\n')
    (package/'backend/main.py').write_text('# newer synthetic backend\n')
    installer.install(target, package, shortcut=False)
    assert (target/'backend/main.py').read_text() == '# newer synthetic backend\n'
    installer.uninstall(target)
    assert (tmp_path/'xdg/scottai/runtimes'/('a'*64)/'runtime/bin/python').is_file()
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


@pytest.mark.skipif(sys.platform!='linux',reason='External Linux venv pointer')
def test_retry_repairs_partial_environment(tmp_path, package, monkeypatch):
    target = tmp_path/'retry'
    calls = []
    monkeypatch.setenv('XDG_DATA_HOME',str(tmp_path/'xdg'))
    def environment(root, recorded):
        runtime = Path(recorded)/'runtime'
        runtime.mkdir(parents=True,exist_ok=True)
        calls.append(True)
        if len(calls) == 1:
            raise subprocess.CalledProcessError(1, ['synthetic-venv'])
        (runtime/'bin').mkdir()
        (runtime/'bin/python').write_text('synthetic')
        (runtime/'pyvenv.cfg').write_text('synthetic')
        return runtime/'bin/python'
    monkeypatch.setattr(installer, 'ensure_external_runtime', environment)
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


@pytest.mark.skipif(sys.platform!='linux',reason='Linux runtime symlink')
def test_uninstall_removes_owned_broken_pointer_and_preserves_external_files(tmp_path):
    prefix=tmp_path/'app';prefix.mkdir()
    external=tmp_path/'persistent';external.mkdir()
    (external/'preserve.txt').write_text('independent component')
    (prefix/'runtime').symlink_to(external/'runtime',target_is_directory=True)
    (prefix/installer.MARKER).write_text(json.dumps(dict(files=[],runtime_owned=True,
        runtime_home=str(external),shortcut='')))
    # Pointer ownership must match exactly, even when the target was removed.
    installer.uninstall(prefix)
    assert not (prefix/'runtime').is_symlink()
    assert (external/'preserve.txt').read_text()=='independent component'
