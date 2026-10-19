"""Private Python paths, ownership and real venv persistence; synthetic stores only."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import pytest

import linux_runtime as runtime


@pytest.fixture
def package(tmp_path, monkeypatch):
    root=tmp_path/'package'
    core={}
    for name in runtime.CORE:
        file=root/'python-runtime'/name
        file.parent.mkdir(parents=True,exist_ok=True)
        file.write_bytes(b'synthetic interpreter never executed')
        core[name]=hashlib.sha256(file.read_bytes()).hexdigest()
    (root/'python-runtime/.scott-python.json').write_text(json.dumps(
        dict(version='3.13.16',sha256='a'*64,core=core)))
    monkeypatch.setenv('XDG_DATA_HOME',str(tmp_path/'private data'))
    return root


def test_receipt_damage_rejected_before_destination_creation(package,tmp_path):
    (package/'python-runtime/bin/python3.13').write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='повреждены'):
        runtime.read_receipt(package/'python-runtime')
    assert not (tmp_path/'private data').exists()


@pytest.mark.parametrize('sha',['../../escape','x'*64,'a'*63,True])
def test_receipt_rejects_invalid_slot_identifier(package,sha):
    path=package/'python-runtime/.scott-python.json'
    value=json.loads(path.read_text());value['sha256']=sha
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='проверенный'):
        runtime.read_receipt(path.parent)


def test_slot_is_independent_of_mount_and_relative_xdg(package,tmp_path,monkeypatch):
    receipt=runtime.read_receipt(package/'python-runtime')
    expected=tmp_path/'private data/scottai/runtimes'/('a'*64)
    assert runtime.slot_path(receipt)==expected
    monkeypatch.setenv('XDG_DATA_HOME','relative')
    monkeypatch.setattr(Path,'home',lambda:tmp_path/'home')
    assert runtime.slot_path(receipt)==tmp_path/'home/.local/share/scottai/runtimes'/('a'*64)
    assert runtime.slot_path(receipt,str(expected))==expected


@pytest.mark.skipif(sys.platform!='linux',reason='Linux flock and private modes')
def test_foreign_slot_and_symlink_are_preserved(package,tmp_path):
    slot=runtime.slot_path(runtime.read_receipt(package/'python-runtime'))
    slot.mkdir(parents=True)
    (slot/'personal').write_bytes(b'preserve')
    with pytest.raises(ValueError,match='не принадлежит'):
        runtime.ensure(package)
    assert (slot/'personal').read_bytes()==b'preserve'
    linked=tmp_path/'linked'
    linked.symlink_to(slot,target_is_directory=True)
    with pytest.raises(ValueError,match='ссылку'):
        runtime.no_links(linked/'child')


@pytest.mark.skipif(sys.platform!='linux',reason='Linux flock')
def test_busy_lock_times_out_without_stealing_owner(package,tmp_path):
    path=tmp_path/'owned.lock'
    with runtime.locked(path):
        with pytest.raises(ValueError,match='другим процессом'):
            with runtime.locked(path,timeout=0):
                pytest.fail('must not acquire busy lock')
    with runtime.locked(path,timeout=0):
        pass


def test_voice_home_uses_external_data_and_preserves_legacy(package,monkeypatch,tmp_path):
    import scott_voice_install as voice
    import storage_paths
    monkeypatch.setattr(storage_paths.sys,'platform','linux')
    monkeypatch.delenv('SCOTT_STORAGE_MODE',raising=False)
    monkeypatch.delenv('SCOTT_VOICE_HOME',raising=False)
    (package/'.scott-linux-install.json').write_text('{}')
    external=tmp_path/'private data/scottai/components/voice-runtime'
    assert voice.home_path(package)==external
    external.mkdir(parents=True)
    (external/'scott-install.json').write_text('{"ready":true}')
    import scott_voice_engine
    assert scott_voice_engine.default_config(package).python==voice.python_path(external)
    old=package/'voice-runtime'
    old.mkdir();(old/'scott-install.json').write_text('{"ready":true}')
    assert voice.home_path(package)==old
    monkeypatch.setenv('SCOTT_VOICE_HOME',str(tmp_path/'override'))
    assert voice.home_path(package)==tmp_path/'override'


@pytest.mark.skipif(sys.platform!='linux',reason='Linux owned slot recovery')
@pytest.mark.parametrize('readonly',[False,True])
def test_interrupted_venv_retries_and_ready_environment_is_not_recreated(package,monkeypatch,readonly):
    if readonly:(package/'python-runtime').chmod(0o555)
    calls=[]
    def child(command,**kwargs):
        calls.append(command)
        if '-m' in command:
            home=Path(command[-1]);(home/'bin').mkdir(parents=True,exist_ok=True)
            (home/'bin/python').write_text('fixture')
            (home/'pyvenv.cfg').write_text('fixture configuration')
            if len(calls)==1:raise subprocess.CalledProcessError(1,command)
            return subprocess.CompletedProcess(command,0)
        slot=Path(command[0]).parents[2]
        return subprocess.CompletedProcess(command,0,json.dumps(dict(
            base=str(slot/'python-runtime'),prefix=str(slot/'runtime'),version=[3,13])))
    monkeypatch.setattr(runtime.subprocess,'run',child)
    with pytest.raises(subprocess.CalledProcessError):runtime.ensure(package)
    python=runtime.ensure(package)
    marker=python.parents[2]/runtime.OWNER
    assert json.loads(marker.read_text())['ready']
    assert marker.stat().st_mode&0o777==0o600
    python.write_text('preserved installed dependencies sentinel')
    assert runtime.ensure(package)==python
    assert python.read_text()=='preserved installed dependencies sentinel'
    assert sum('-m' in call for call in calls)==2
    dependency=python.parent.parent/'preserved-dependency'
    dependency.write_text('keep across interpreter repair')
    python.unlink()
    assert runtime.ensure(package)==python
    assert dependency.read_text()=='keep across interpreter repair'
    assert sum('-m' in call for call in calls)==3
