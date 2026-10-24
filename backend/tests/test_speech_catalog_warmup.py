"""Prewarm only the Windows inventory; keep the recognizer prompt unchanged."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import httpx
import pytest
import app_resolver as resolver
import speech_hints as hints

pytestmark=pytest.mark.unit


@pytest.fixture
def inventory(monkeypatch):
    hints.reset()
    monkeypatch.setattr(resolver,'IS_WINDOWS',True)
    monkeypatch.setattr(resolver,'_startapps_index_cache',None)
    monkeypatch.setattr(resolver,'_shortcut_index_cache',None)
    monkeypatch.setattr(resolver,'_index_metadata',{})
    state={'apps':{'google chrome':'synthetic-id'},'shortcuts':{'discord':'synthetic-shortcut'},'calls':[]}
    def apps():state['calls'].append('apps');return dict(state['apps'])
    def shortcuts():state['calls'].append('shortcuts');return dict(state['shortcuts'])
    monkeypatch.setattr(resolver,'_build_startapps_index',apps)
    monkeypatch.setattr(resolver,'_build_shortcut_index',shortcuts)
    yield state
    hints.reset()


def test_prewarm_reads_inventory_without_building_prompt(inventory):
    hints.warm_catalog()
    assert inventory['calls']==['apps','shortcuts']
    assert hints._cached is None
    assert 'Google Chrome' in hints.prompt() and 'Discord' in hints.prompt()
    assert inventory['calls']==['apps','shortcuts']


@pytest.mark.parametrize('names',[[],['Google Chrome'],['Discord','Visual Studio Code'],hints.KNOWN_APPS])
def test_prewarmed_prompt_is_exactly_the_same_as_cold_prompt(inventory,monkeypatch,names):
    inventory['apps']={name.casefold():'synthetic-id' for name in names}
    inventory['shortcuts']={}
    cold=hints.prompt()
    hints.reset()
    monkeypatch.setattr(resolver,'_startapps_index_cache',None)
    monkeypatch.setattr(resolver,'_shortcut_index_cache',None)
    inventory['calls'].clear()
    hints.warm_catalog()
    assert hints._cached is None
    assert hints.prompt()==cold


@pytest.mark.parametrize('failed',['_get_startapps_index','_get_shortcut_index'])
def test_one_unavailable_inventory_source_does_not_stop_the_other(inventory,monkeypatch,failed):
    def unavailable():raise OSError('synthetic unavailable source')
    monkeypatch.setattr(resolver,failed,unavailable)
    hints.warm_catalog()
    assert hints._cached is None
    assert inventory['calls']==(['shortcuts'] if failed=='_get_startapps_index' else ['apps'])


def test_non_windows_prewarm_does_not_run_windows_discovery(inventory,monkeypatch):
    monkeypatch.setattr(resolver,'IS_WINDOWS',False)
    hints.warm_catalog()
    assert inventory['calls']==[] and hints._cached is None


def test_existing_prompt_does_not_start_an_unneeded_scan(inventory):
    prompt=hints.prompt()
    inventory['calls'].clear()
    hints.warm_catalog()
    assert inventory['calls']==[] and hints.prompt()==prompt


def test_empty_prefetch_leaves_normal_discovery_a_retry(inventory):
    inventory['apps']={}
    hints.warm_catalog()
    assert resolver._startapps_index_cache is None and hints._cached is None
    inventory['apps']={'google chrome':'synthetic-id'}
    assert 'Google Chrome' in hints.prompt()
    assert inventory['calls']==['apps','shortcuts','apps']


def test_prewarm_does_not_discard_an_existing_empty_snapshot(inventory,monkeypatch):
    monkeypatch.setattr(resolver,'_startapps_index_cache',{})
    hints.warm_catalog()
    assert resolver._startapps_index_cache=={} and inventory['calls']==['shortcuts']


def test_early_prompt_shares_the_inflight_inventory_build(inventory,monkeypatch):
    entered,release=Event(),Event()
    calls=[]
    def build():
        calls.append('apps');entered.set();assert release.wait(3)
        return inventory['apps']
    monkeypatch.setattr(resolver,'_build_startapps_index',build)
    with ThreadPoolExecutor(max_workers=2) as pool:
        warm=pool.submit(hints.warm_catalog)
        assert entered.wait(2)
        prompt=pool.submit(hints.prompt)
        try:assert not prompt.done()
        finally:release.set()
        warm.result(timeout=3)
        assert 'Google Chrome' in prompt.result(timeout=3)
    assert calls==['apps'] and inventory['calls']==['shortcuts']


def test_prefetch_does_not_freeze_prompt_before_explicit_catalog_refresh(inventory):
    hints.warm_catalog()
    inventory['apps']={'spotify':'synthetic-id'}
    inventory['shortcuts']={}
    resolver.refresh_index()
    prompt=hints.prompt()
    assert 'Spotify' in prompt and 'Google Chrome' not in prompt


@pytest.fixture
def startup(main_module,monkeypatch):
    import scott_voice_engine,voice_install_jobs,voice_prepare,browser_control_jobs
    monkeypatch.setattr(main_module,'WARMUP_MODELS',True)
    monkeypatch.setattr(main_module,'_start_parent_watch',lambda:None)
    monkeypatch.setattr(scott_voice_engine,'cancel',lambda:None)
    for job in (voice_install_jobs.jobs,voice_prepare.preparation,browser_control_jobs.jobs):
        monkeypatch.setattr(job,'close',lambda:None)
    return main_module


def test_startup_catalog_and_recognition_are_parallel_and_health_stays_available(startup,monkeypatch):
    main=startup
    entered,release=Event(),Event()
    def catalog():entered.set();assert release.wait(3)
    monkeypatch.setattr(hints,'warm_catalog',catalog,raising=False)
    async def check():
        recognition=asyncio.Event()
        async def warm_recognition():
            recognition.set()
            await asyncio.Event().wait()
        monkeypatch.setattr(main,'_warmup_models',warm_recognition)
        try:
            async with main.lifespan(main.app):
                await asyncio.wait_for(recognition.wait(),1)
                assert await asyncio.to_thread(entered.wait,2)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://localhost') as client:
                    response=await asyncio.wait_for(client.get('/health'),1)
                    assert response.status_code==200 and response.json()['status']=='online'
        finally:release.set()
    asyncio.run(check())


def test_disabled_warmup_does_not_start_inventory_or_models(startup,monkeypatch):
    main=startup
    monkeypatch.setattr(main,'WARMUP_MODELS',False)
    async def forbidden():pytest.fail('Disabled startup warmup must not run')
    monkeypatch.setattr(main,'_warmup_models',forbidden)
    monkeypatch.setattr(main,'_warmup_app_catalog',forbidden,raising=False)
    async def check():
        async with main.lifespan(main.app):await asyncio.sleep(0)
    asyncio.run(check())


def test_catalog_failure_is_optional_and_does_not_expose_provider_error(startup,monkeypatch,capsys):
    def fail():raise RuntimeError('synthetic-private-provider-error')
    monkeypatch.setattr(hints,'warm_catalog',fail,raising=False)
    asyncio.run(startup._warmup_app_catalog())
    assert 'synthetic-private-provider-error' not in capsys.readouterr().out


def test_shutdown_cancels_catalog_wait_without_starting_voice(startup,monkeypatch):
    main=startup;entered,release=Event(),Event();tasks=[]
    async def no_models():pass
    monkeypatch.setattr(main,'_warmup_models',no_models)
    def catalog():entered.set();assert release.wait(3)
    monkeypatch.setattr(hints,'warm_catalog',catalog,raising=False)
    original=main._warmup_app_catalog
    async def recorded():
        tasks.append(asyncio.current_task())
        await original()
    monkeypatch.setattr(main,'_warmup_app_catalog',recorded)
    async def check():
        try:
            async with main.lifespan(main.app):assert await asyncio.to_thread(entered.wait,2)
            await asyncio.sleep(0)
            assert len(tasks)==1 and tasks[0].cancelled()
        finally:release.set()
    asyncio.run(check())
