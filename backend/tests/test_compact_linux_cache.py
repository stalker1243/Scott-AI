"""The torchless Linux profile can safely retain completed pip downloads too."""
from pathlib import Path
from types import SimpleNamespace

import pytest
import bootstrap
import installation_space
import setup_cache

pytestmark=pytest.mark.unit


@pytest.mark.parametrize('platform', ['posix','nt'])
@pytest.mark.parametrize('success', [True, False])
def test_managed_compact_cache_is_reused_and_only_cleared_after_success(tmp_path,monkeypatch,platform,success):
    root=tmp_path/'application'
    script=root/'backend/bootstrap.py';script.parent.mkdir(parents=True);script.touch()
    executable=root/'runtime/bin/python'
    executable.parent.mkdir(parents=True)
    executable.touch()
    expected=root/'runtime/.scott-downloads/pip-cache'
    monkeypatch.setattr(bootstrap,'__file__',str(script))
    # Change only this module's OS view; pathlib/other threads keep their real OS.
    monkeypatch.setattr(bootstrap,'os',SimpleNamespace(name=platform))
    monkeypatch.setattr(installation_space,'require_space',lambda *args: None)
    monkeypatch.setattr(bootstrap,'ensure_pip',lambda *args: None)
    calls=[]
    payload=b'completed fixture wheel'
    def pip(executable,arguments,progress,message,**kwargs):
        cache=kwargs['cache_directory']
        assert cache==expected
        calls.append(list(arguments))
        if len(calls)==1:
            setup_cache.prepare(cache)
            (cache/'http-v2').mkdir()
            (cache/'http-v2/completed.whl').write_bytes(payload)
        else:
            assert (cache/'http-v2/completed.whl').read_bytes()==payload
        return (success or len(calls)==1),'controlled dependency failure'
    monkeypatch.setattr(bootstrap,'_run_pip',pip)
    result=bootstrap._install_compact_dependencies(str(executable),None)
    assert result.done is success
    assert len(calls)==2
    if success:
        assert not (expected/'http-v2/completed.whl').exists()
    else:
        assert (expected/'http-v2/completed.whl').read_bytes()==payload
        assert 'controlled dependency failure' in result.error
