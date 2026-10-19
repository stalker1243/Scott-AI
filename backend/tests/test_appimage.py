"""AppImage packaging must refuse private, installed or externally linked trees."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('build_appimage', ROOT/'installer/build_appimage.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


@pytest.fixture
def package(tmp_path):
    root = tmp_path/'package'
    for name in ('launcher/ScottAIQt', 'launcher/ScottAIUpdater', 'launcher/qt.conf',
                 'backend/linux_runtime.py', 'backend/storage_paths.py', 'backend/update_package.py', 'backend/update_appimage.py',
                 'python-runtime/.scott-python.json', 'assets/brand/icon-256.png',
                 'run.sh', 'python-environment.sh'):
        file = root/name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b'fixture')
    (root/'VERSION.json').write_text(json.dumps(dict(version='2.0.1')))
    return root


@pytest.mark.parametrize('name', ['.env', 'runtime', '.scott-linux-install.json',
                                 'backend/data/chats.json', 'backend/output.log',
                                 'backend/__pycache__/main.pyc'])
def test_personal_files_stop_packaging(package, name):
    file = package/name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(b'private fixture')
    with pytest.raises(ValueError):
        builder.validate_package(package)
    assert file.read_bytes() == b'private fixture'


@pytest.mark.skipif(os.name == 'nt', reason='POSIX vendor links')
def test_internal_links_work_external_links_stop_packaging(package, tmp_path):
    linked = package/'python-runtime/python'
    linked.symlink_to('.scott-python.json')
    assert builder.validate_package(package) == '2.0.1'
    linked.unlink()
    external = tmp_path/'private'
    external.write_bytes(b'private fixture')
    linked.symlink_to(external)
    with pytest.raises(ValueError, match='External link'):
        builder.validate_package(package)
    assert external.read_bytes() == b'private fixture'


def test_bad_cached_tool_never_executes_or_downloads(tmp_path, monkeypatch):
    cache = tmp_path/'tools'
    cache.mkdir()
    tool = cache/'appimagetool.AppImage'
    tool.write_bytes(b'corrupt fixture')
    monkeypatch.setattr(builder.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('Network called'))
    with pytest.raises(ValueError, match='checksum mismatch'):
        builder.tools(cache)
    assert tool.read_bytes() == b'corrupt fixture'


def test_offline_build_does_not_download(tmp_path, monkeypatch):
    monkeypatch.setattr(builder.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('Network called'))
    with pytest.raises(ValueError, match='offline mode'):
        builder.tools(tmp_path/'empty', offline=True)


def test_existing_image_preserved_before_tool_preparation(package, tmp_path, monkeypatch):
    output = tmp_path/'ScottAI.AppImage'
    output.write_bytes(b'previous image')
    monkeypatch.setattr(builder, 'tools', lambda *a, **k: pytest.fail('Tools prepared'))
    with pytest.raises(ValueError, match='overwrite'):
        builder.build(package, output, tmp_path/'cache')
    assert output.read_bytes() == b'previous image'


@pytest.mark.skipif(os.name=='nt',reason='AppDir uses POSIX symlinks')
def test_build_accepts_notices_already_copied_by_linux_builder(package,tmp_path,monkeypatch):
    root=tmp_path/'source'
    for name in ('installer/linux/AppRun','installer/linux/com.scottai.launcher.desktop',
                 'installer/licenses/appimage/LICENSE.txt'):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'pinned source notice')
    existing=package/'licenses/appimage/LICENSE.txt';existing.parent.mkdir(parents=True);existing.write_bytes(b'previous notice')
    cache=tmp_path/'tools';cache.mkdir()
    monkeypatch.setattr(builder,'ROOT',root)
    monkeypatch.setattr(builder,'tools',lambda *a,**k:cache)
    def run(command,**kwargs):
        if '--appimage-extract' in command:
            script=Path(kwargs['cwd'])/'squashfs-root/AppRun';script.parent.mkdir();script.write_bytes(b'tool fixture')
        else:
            appdir=Path(command[-2])
            assert (appdir/'licenses/appimage/LICENSE.txt').read_bytes()==b'pinned source notice'
            Path(command[-1]).write_bytes(b'synthetic AppImage fixture')
        return subprocess.CompletedProcess(command,0)
    monkeypatch.setattr(builder.subprocess,'run',run)
    output=tmp_path/'new.AppImage';result=builder.build(package,output,cache,offline=True)
    assert output.read_bytes()==b'synthetic AppImage fixture' and result['sha256']==builder.digest(output)
    assert existing.read_bytes()==b'previous notice'


@pytest.mark.skipif(os.name == 'nt', reason='Linux AppRun')
def test_apprun_preserves_arguments_cwd_and_exit_status(tmp_path):
    root = tmp_path/'Scott AI Юникод'
    root.mkdir()
    (root/'AppRun').write_bytes((ROOT/'installer/linux/AppRun').read_bytes())
    (root/'run.sh').write_text('#!/bin/bash\nprintf "%s\\n" "$PWD" "$@"\nexit 17\n')
    result = subprocess.run(['bash', str(root/'AppRun'), '--name', 'quoted "имя" $value'],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 17
    assert result.stdout.splitlines() == [str(tmp_path), '--name', 'quoted "имя" $value']
