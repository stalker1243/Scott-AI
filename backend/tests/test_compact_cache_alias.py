"""Canonical cache paths must be bound to a verified app-owned Linux runtime."""
from pathlib import Path
from types import SimpleNamespace
import pytest
import bootstrap
import linux_runtime
import installation_space
import setup_cache

pytestmark=pytest.mark.unit

@pytest.fixture
def alias(tmp_path,monkeypatch):
    root=tmp_path/'app';(root/'backend').mkdir(parents=True)
    script=root/'backend/bootstrap.py';script.touch()
    slot=tmp_path/'owned-slot/runtime';(slot/'bin').mkdir(parents=True)
    (slot/'bin/python').touch()
    try:
        (root/'runtime').symlink_to(slot,target_is_directory=True)
    except OSError:
        pytest.skip('Directory symlinks unavailable on this test account')
    monkeypatch.setattr(bootstrap,'__file__',str(script))
    monkeypatch.setattr(bootstrap,'os',SimpleNamespace(name='posix'))
    monkeypatch.setattr(installation_space,'require_space',lambda *a:None)
    monkeypatch.setattr(bootstrap,'ensure_pip',lambda *a:None)
    return root,slot

def test_verified_runtime_alias_uses_canonical_owned_cache(alias,monkeypatch):
    root,slot=alias
    checks=[]
    def selected(path):
        assert path==root
        checks.append(path)
        return slot/'bin/python'
    monkeypatch.setattr(linux_runtime,'selected',selected)
    calls=[]
    def pip(*args,**kwargs):
        assert args[0]==str(slot/'bin/python')
        cache=kwargs['cache_directory']
        assert cache==slot/'.scott-downloads/pip-cache'
        setup_cache.prepare(cache)
        calls.append(cache)
        return True,''
    monkeypatch.setattr(bootstrap,'_run_pip',pip)
    result=bootstrap._install_compact_dependencies(str(root/'runtime/bin/python'),None)
    assert result.done,result.error
    assert len(checks)==1 and len(calls)==2
    assert (slot/'.scott-downloads/pip-cache/.scott-cache.json').is_file()

def test_alias_to_unregistered_target_stops_before_pip(alias,tmp_path,monkeypatch):
    root,foreign=alias
    registered=tmp_path/'registered/runtime'
    registered.mkdir(parents=True)
    keep=foreign/'keep.txt';keep.write_bytes(b'foreign content')
    monkeypatch.setattr(linux_runtime,'selected',lambda path:registered/'bin/python')
    monkeypatch.setattr(bootstrap,'ensure_pip',lambda *a:pytest.fail('No pip on an unregistered alias'))
    monkeypatch.setattr(bootstrap,'_run_pip',lambda *a,**k:pytest.fail('No install on an unregistered alias'))
    result=bootstrap._install_compact_dependencies(str(root/'runtime/bin/python'),None)
    assert not result.done
    assert 'зарегистрированной' in result.error
    assert keep.read_bytes()==b'foreign content'
    assert not (foreign/'.scott-downloads').exists()

def test_invalid_owned_receipt_stops_before_pip(alias,monkeypatch):
    root,slot=alias
    def invalid(*args):
        raise ValueError('Controlled receipt error')
    monkeypatch.setattr(linux_runtime,'selected',invalid)
    monkeypatch.setattr(bootstrap,'_run_pip',lambda *a,**k:pytest.fail('No install before ownership check'))
    result=bootstrap._install_compact_dependencies(str(root/'runtime/bin/python'),None)
    assert not result.done
    assert 'проверить среду Python' in result.error
    assert not (slot/'.scott-downloads').exists()
