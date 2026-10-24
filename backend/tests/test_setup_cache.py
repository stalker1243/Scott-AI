import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import setup_cache

pytestmark=pytest.mark.unit

def test_managed_pip_reuses_owned_cache_after_failure(boot_cache,tmp_path,monkeypatch):
    boot=boot_cache
    own=tmp_path/'runtime/.scott-downloads/pip-cache'
    global_cache=tmp_path/'global-cache'
    global_cache.mkdir()
    other=global_cache/'keep.whl'
    other.write_bytes(b'unrelated')
    monkeypatch.setenv('PIP_CACHE_DIR',str(global_cache))
    monkeypatch.setattr(boot.subprocess,'run',lambda *a,**kw:SimpleNamespace(stdout=''))
    calls=[]
    payload=own/'http-v2/verified.body'
    def pip(command,consume,timeout,env):
        calls.append(command)
        assert env['PIP_CACHE_DIR']==str(own)
        assert command[command.index('--cache-dir')+1]==str(own)
        assert '--no-cache-dir' not in command
        if len(calls)==1:
            payload.parent.mkdir(parents=True)
            payload.write_bytes(b'cached transfer')
            return 1
        assert payload.read_bytes()==b'cached transfer'
        return 0
    monkeypatch.setattr(boot,'_stream_process',pip)
    assert not boot._run_pip('python',[],None,'fixture',0,1,cache_directory=own)[0]
    assert boot._run_pip('python',[],None,'fixture',0,1,cache_directory=own)[0]
    setup_cache.maintain(own,complete=True)
    assert not payload.exists() and other.read_bytes()==b'unrelated'
    assert json.loads((own/setup_cache.MARKER).read_text())==setup_cache.IDENTITY

@pytest.fixture
def boot_cache():
    import bootstrap
    return bootstrap

def test_runtime_preparation_clears_its_cache_after_success(boot_cache,tmp_path,monkeypatch):
    import installation_space
    boot=boot_cache
    monkeypatch.setattr(boot,'__file__',str(tmp_path/'backend/bootstrap.py'))
    monkeypatch.setattr(boot,'torch_requirement',lambda:([boot.TORCH_CPU_PIN],'fixture'))
    monkeypatch.setattr(boot,'ensure_pip',lambda *args:None)
    monkeypatch.setattr(boot.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(returncode=0,stdout='ok'))
    monkeypatch.setattr(installation_space,'require_space',lambda *args:None)
    cached=[]
    def pip(*args,**kwargs):
        directory=kwargs.get('cache_directory')
        assert bool(directory)==(boot.os.name=='nt')
        if directory:
            setup_cache.prepare(directory)
            payload=directory/'http-v2/body'
            payload.parent.mkdir()
            payload.write_bytes(b'fixture cache')
            cached.append(payload)
        return True,''
    monkeypatch.setattr(boot,'_run_pip',pip)
    executable=tmp_path/('runtime/python.exe' if boot.os.name=='nt' else 'runtime/bin/python')
    assert boot.install_dependencies(str(executable)).done
    assert all(not path.exists() for path in cached)

def test_cache_is_bounded_without_touching_foreign_files(tmp_path):
    own=setup_cache.prepare(tmp_path/'own')
    first=own/'http-v2/first.body'
    first.parent.mkdir()
    first.write_bytes(b'123456')
    second=first.with_name('second.body')
    second.write_bytes(b'abcdef')
    os.utime(first,(1,1))
    foreign=own/'do-not-delete.txt'
    foreign.write_bytes(b'other')
    assert setup_cache.trim(own,6)==6
    assert not first.exists() and second.read_bytes()==b'abcdef'
    setup_cache.trim(own,0)
    assert not second.exists() and foreign.read_bytes()==b'other'

def test_unowned_directory_is_preserved(tmp_path):
    path=tmp_path/'existing'
    path.mkdir()
    other=path/'keep'
    other.write_bytes(b'unchanged')
    with pytest.raises(setup_cache.DownloadError):setup_cache.prepare(path)
    assert other.read_bytes()==b'unchanged'
    assert not (path/setup_cache.MARKER).exists()

def test_unavailable_optional_cache_does_not_block_setup(boot_cache,tmp_path,monkeypatch):
    boot=boot_cache
    directory=tmp_path/'unowned-cache'
    directory.mkdir()
    foreign=directory/'keep.txt'
    foreign.write_bytes(b'keep')
    monkeypatch.setattr(boot.subprocess,'run',lambda *a,**kw:SimpleNamespace(stdout=''))
    calls=[]
    def pip(command,*a,**kw):
        calls.append(command)
        return 0
    monkeypatch.setattr(boot,'_stream_process',pip)
    assert boot._run_pip('python',[],None,'fixture',0,1,cache_directory=directory)[0]
    assert '--no-cache-dir' in calls[0] and '--cache-dir' not in calls[0]
    assert foreign.read_bytes()==b'keep'

def test_hardlinked_cache_is_never_modified(tmp_path):
    own=setup_cache.prepare(tmp_path/'own')
    external=tmp_path/'other'
    external.write_bytes(b'keep')
    (own/'http-v2').mkdir()
    os.link(external,own/'http-v2/body')
    with pytest.raises(setup_cache.DownloadError):setup_cache.trim(own,0)
    assert external.read_bytes()==b'keep' and (own/'http-v2/body').exists()

def test_redirected_cache_is_never_followed(tmp_path):
    own=setup_cache.prepare(tmp_path/'own')
    external=tmp_path/'other'
    external.mkdir()
    try:(own/'http-v2').symlink_to(external,target_is_directory=True)
    except OSError:pytest.skip('Symlinks unavailable')
    with pytest.raises(setup_cache.DownloadError):setup_cache.trim(own,0)
    assert not list(external.iterdir())
