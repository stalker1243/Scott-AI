"""Release surface: local voice only, unchanged preferences and canonical assets."""
import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import listen_endpoints
import scott_voice_install as installer
import voice_config
from scott_voice_engine import config_at
from test_scott_voice_engine import integrated

pytestmark=pytest.mark.unit
ROOT=Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('method',['get','post'])
def test_retired_configuration_route_is_unavailable(main_module,method):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main_module.app),base_url='http://localhost') as client:
            response=await getattr(client,method)('/listen/configuration')
            assert response.status_code==404
    asyncio.run(run())


def test_catalog_read_preserves_accepted_speech_preferences(main_module,integrated):
    voice_config.save_voice('scott-voice',profile='scott',streaming=True,acceleration=True,buffer_mode='4s')
    before=voice_config.CONFIG_PATH.read_bytes()
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main_module.app),base_url='http://localhost') as client:
            response=await client.get('/voice/available');assert response.status_code==200
            data=response.json()
            assert 'input' not in data
            assert data['scott_profile']=='scott' and data['scott_streaming'] and data['scott_acceleration']
            assert data['scott_buffer']=='4s'
            assert 'adaptive' not in [value['id'] for value in data['scott_buffers']]
    asyncio.run(run())
    assert voice_config.CONFIG_PATH.read_bytes()==before


def test_old_cloud_preference_cannot_replace_local_listener(tmp_path,monkeypatch):
    legacy=tmp_path/'live_voice_config.json'
    payload=json.dumps(dict(mode='gpt-live',api_key='synthetic-retired-secret')).encode()
    legacy.write_bytes(payload)
    calls=[];active=[False]
    def start():calls.append('start');active[0]=True;return dict(success=True)
    def stop():calls.append('stop');active[0]=False;return dict(success=True)
    listener=SimpleNamespace(start=start,stop=stop,status=lambda:dict(listening=active[0],available=True))
    preparation=SimpleNamespace(listening_requested=lambda:1,listening_stopped=lambda:1,
        start_listening=lambda ident:None,listening_failed=lambda ident:ident,
        cancel_listening=lambda ident:None,snapshot=lambda:dict(state='idle'))
    monkeypatch.setattr(listen_endpoints.scott_runtime,'listener',listener)
    monkeypatch.setattr(listen_endpoints,'_voice_preparation',lambda:preparation)
    app=FastAPI();app.include_router(listen_endpoints.router)
    with TestClient(app) as client:
        assert client.post('/listen/start').json()['listening']
        assert client.get('/listen/status').json()['listening']
        assert not client.post('/listen/stop').json()['listening']
    assert calls==['start','stop'] and legacy.read_bytes()==payload


def test_retired_token_still_redacts_in_support_output(tmp_path):
    import support_logs
    path=tmp_path/'backend/data/live_voice_config.json';path.parent.mkdir(parents=True)
    path.write_text(json.dumps(dict(api_key='synthetic-retired-secret')),encoding='utf8')
    assert 'synthetic-retired-secret' not in support_logs.redact('failed synthetic-retired-secret',tmp_path)


def test_production_helpers_bundle_from_canonical_sources_without_layout_migration(tmp_path):
    sources=installer.asset_sources(ROOT)
    for name in installer.ASSETS[:7]:
        assert sources[name]==ROOT/'voice/runtime'/Path(name).name
    destination=tmp_path/'voice-assets';installer.bundle_assets(destination,ROOT)
    for name in installer.ASSETS:
        assert (destination/name).read_bytes()==sources[name].read_bytes()
    assert not (destination/'backend/gpt_live.py').exists()


def test_existing_sdk_paths_stay_unchanged(tmp_path):
    config=config_at(tmp_path)
    assert config.worker==tmp_path/'experiments/voice_design/voice_worker.py'
    assert config.model_dir==tmp_path/'experiments/voice_design/models/base'
    runtime=tmp_path/'voice/runtime';runtime.mkdir(parents=True)
    relocated=config_at(tmp_path)
    assert relocated.worker==runtime/'voice_worker.py'
    assert relocated.profiles_json==runtime/'robotic_profiles.json'
    assert relocated.python==config.python and relocated.model_dir==config.model_dir


def test_cloud_implementation_is_absent_from_distribution_sources():
    for name in ('gpt_live.py','live_audio.py','voice_mode.py'):
        assert not (ROOT/'backend'/name).exists()
