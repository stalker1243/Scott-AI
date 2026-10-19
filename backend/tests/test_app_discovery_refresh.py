"""Catalog changes and concurrent discovery, without inspecting installed apps."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import time
import pytest
import app_resolver as resolver

pytestmark=pytest.mark.unit


def test_catalog_refresh_is_single_flight_and_returns_snapshots(monkeypatch):
    monkeypatch.setattr(resolver,'_desktop_index_cache',None)
    monkeypatch.setattr(resolver,'_index_metadata',{})
    calls=[]
    def build():
        calls.append(1);time.sleep(.02);return {'fixture':'fixture.desktop'}
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:resolver._cached_index('desktop',build),range(8)))
    assert len(calls)==1
    results[0].clear()
    assert resolver._cached_index('desktop',build)=={'fixture':'fixture.desktop'}
    identity,built=resolver._index_metadata['desktop']
    resolver._index_metadata['desktop']=(identity,built-resolver.INDEX_TTL-1)
    assert resolver._cached_index('desktop',lambda:{'new':'new.desktop'})=={'new':'new.desktop'}
    assert resolver._cached_index('desktop',lambda:{},force=True)=={'new':'new.desktop'}


def test_new_install_on_lookup_miss_refreshes_once_then_throttles(monkeypatch):
    now=time.monotonic();calls=[];found=[]
    monkeypatch.setattr(resolver,'_index_metadata',{'desktop':(1,now-4)})
    monkeypatch.setattr(resolver,'_last_miss_refresh',0.)
    monkeypatch.setattr(resolver,'_resolve_cached_app',lambda name:found[0] if found else None)
    def refresh():
        calls.append(1);found.append('newly-installed')
    monkeypatch.setattr(resolver,'refresh_index',refresh)
    assert resolver.resolve_app('Fixture')=='newly-installed'
    assert len(calls)==1
    found.clear()
    assert resolver.resolve_app('Missing') is None
    assert len(calls)==1


def test_path_execution_alias_needs_no_handwritten_mapping(monkeypatch):
    monkeypatch.setattr(resolver,'IS_WINDOWS',True)
    monkeypatch.setattr(resolver,'IS_MACOS',False)
    monkeypatch.setattr(resolver,'_resolve_app_paths',lambda _:None)
    monkeypatch.setattr(resolver.shutil,'which',lambda _:r'C:\fixture\NovelEditor.exe')
    monkeypatch.setattr(resolver,'_get_startapps_index',lambda:pytest.fail('PATH match needs no catalog scan'))
    result=resolver.resolve_app('NovelEditor')
    assert result.kind=='path' and result.source=='path' and result.target.endswith('NovelEditor.exe')


@pytest.mark.parametrize('name',[None,'','x'*257,'app\nshutdown','app\x00name'])
def test_malformed_lookup_never_scans_system(monkeypatch,name):
    monkeypatch.setattr(resolver,'_resolve_cached_app',lambda _:pytest.fail('Invalid lookup reached system'))
    assert resolver.resolve_app(name) is None


def test_startapps_bad_records_are_ignored(monkeypatch):
    import json
    monkeypatch.setattr(resolver,'IS_WINDOWS',True)
    received=[]
    def run(*args,**kwargs):
        received.append(kwargs)
        return SimpleNamespace(returncode=0,stdout=json.dumps([None,{},dict(Name=123,AppID='bad'),dict(Name='Fixture App',AppID='fixture.id')]))
    monkeypatch.setattr(resolver.subprocess,'run',run)
    assert resolver._build_startapps_index()=={'fixture app':'fixture.id'}
    assert received[0]['timeout']==8


def test_linux_discovery_honors_absolute_xdg_and_user_precedence(tmp_path,monkeypatch):
    import os
    user,system=tmp_path/'user',tmp_path/'system'
    dirs=resolver._linux_desktop_dirs({'XDG_DATA_HOME':str(user),'XDG_DATA_DIRS':os.pathsep.join(['relative',str(system)])},tmp_path/'home')
    assert dirs[:2]==[str(user/'applications'),str(system/'applications')]
    assert not any(path.startswith('relative') for path in dirs)
    for parent in (user,system):(parent/'applications').mkdir(parents=True)
    (system/'applications/same.desktop').write_text('[Desktop Entry]\nName=System Fixture\nType=Application\nExec=fixture\n')
    (user/'applications/same.desktop').write_text('[Desktop Entry]\nHidden=true\n')
    (user/'applications/novel.desktop').write_text('[Desktop Entry]\nName=Novel Fixture\nType=Application\nExec=fixture\n')
    monkeypatch.setattr(resolver,'DESKTOP_DIRS',dirs)
    index=resolver._build_desktop_index()
    assert index=={'novel fixture':str(user/'applications/novel.desktop')}
    defaults=resolver._linux_desktop_dirs({'XDG_DATA_HOME':'relative'},tmp_path/'home')
    assert defaults[0]==str(tmp_path/'home/.local/share/applications')
