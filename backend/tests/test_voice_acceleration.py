"""Opt-in acceleration, recipe separation and cancellation without models/devices."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import asyncio
import json

import httpx
import pytest

import scott_voice
import scott_voice_engine as engine_module
import voice_config
from scott_voice_process import VoiceProcessError,recipe_id,audio_key
from test_scott_voice_engine import integrated
from test_scott_voice_process import config

pytestmark=pytest.mark.unit


@pytest.mark.parametrize('value',[None,False,1,'true',{},[]])
def test_acceleration_requires_an_explicit_boolean_true(value):
    voice_config.CONFIG_PATH.write_text(json.dumps({'scott_acceleration':value}))
    assert not voice_config.get_scott_acceleration()


def test_acceleration_is_preserved_across_voice_and_profile_changes():
    assert not voice_config.get_scott_acceleration()
    voice_config.save_voice('eugene')
    voice_config.save_voice('scott-voice',acceleration=True)
    voice_config.save_voice('scott-voice',profile='digital',streaming=True)
    voice_config.save_voice('eugene')
    assert voice_config.get_scott_acceleration() and voice_config.get_scott_streaming()
    assert voice_config.get_scott_profile()=='digital'
    assert voice_config.get_fallback_voice('demo',['demo','eugene'])=='eugene'


def test_benchmark_defaults_are_independent_of_application_preferences(monkeypatch):
    config=engine_module.default_config()
    monkeypatch.setattr(engine_module,'default_config',lambda:config)
    voice_config.save_voice('scott-voice',acceleration=True)
    assert not engine_module.default_config().rms_norm
    assert engine_module.preferred_config().rms_norm
    monkeypatch.setattr(engine_module,'default_config',lambda:replace(config,device='cpu'))
    assert not engine_module.preferred_config().rms_norm
    assert voice_config.get_scott_acceleration()


def test_acceleration_has_its_own_audio_recipe(config):
    original=recipe_id(config);accelerated=recipe_id(replace(config,rms_norm=True))
    assert original!=accelerated
    assert audio_key(original,'Готово.','natural')!=audio_key(accelerated,'Готово.','natural')


def test_switching_back_creates_a_new_worker_with_original_config(integrated):
    configs=[];factory=integrated.engine.factory
    def create(config,**options):
        configs.append(config.rms_norm)
        return factory(config,**options)
    integrated.engine.factory=create
    integrated.engine.synthesize('original')
    original=integrated.clients[-1]
    integrated.engine.set_acceleration(True)
    assert original.closed and integrated.engine.describe()['accelerated']
    integrated.engine.synthesize('fast')
    fast=integrated.clients[-1]
    integrated.engine.set_acceleration(False)
    assert fast.closed and not integrated.engine.describe()['accelerated']
    integrated.engine.synthesize('original again')
    assert configs==[False,True,False]


def test_mode_change_cancels_in_flight_and_queued_generation(integrated):
    integrated.engine.synthesize('prepare')
    client=integrated.clients[0];client.started.clear();client.block=True
    generation=integrated.engine.generation
    with ThreadPoolExecutor() as pool:
        request=pool.submit(integrated.engine.synthesize,'old',generation=generation)
        assert client.started.wait(1)
        integrated.engine.set_acceleration(True)
        with pytest.raises(VoiceProcessError,match='cancelled'): request.result(timeout=2)
    with pytest.raises(VoiceProcessError,match='cancelled'):
        integrated.engine.synthesize('queued',generation=generation)


def test_api_validates_and_applies_acceleration_without_losing_other_preferences(main_module,integrated,monkeypatch):
    voice_config.save_voice('eugene')
    voice_config.save_voice('scott-voice',profile='restrained',streaming=True)
    monkeypatch.setattr(integrated.engine,'describe',lambda:dict(available=True,acceleration_available=True))
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main_module.app),base_url='http://test') as client:
            for voice,value in [('scott-voice',None),('scott-voice',1),('scott-voice','true'),('eugene',True)]:
                assert (await client.post('/voice/select',json={'voice':voice,'acceleration':value})).status_code==400
                assert not voice_config.get_scott_acceleration()
            assert (await client.post('/voice/select',json={'voice':'scott-voice','acceleration':True})).status_code==200
            assert integrated.engine.config.rms_norm and voice_config.get_scott_acceleration()
            assert voice_config.get_scott_profile()=='restrained' and voice_config.get_scott_streaming()
            assert voice_config.get_fallback_voice('demo',['demo','eugene'])=='eugene'
            catalog=(await client.get('/voice/available')).json()
            assert catalog['scott_acceleration'] is True
            monkeypatch.setattr(integrated.engine,'describe',lambda:dict(available=True,acceleration_available=False))
            assert (await client.post('/voice/select',json={'voice':'scott-voice','acceleration':True})).status_code==503
            assert voice_config.get_scott_acceleration()
            assert (await client.post('/voice/select',json={'voice':'scott-voice','acceleration':False})).status_code==200
            assert not integrated.engine.config.rms_norm and not voice_config.get_scott_acceleration()
    asyncio.run(run())


def test_failed_preference_write_does_not_change_the_running_mode(integrated,monkeypatch):
    voice_config.save_voice('scott-voice')
    generation=integrated.engine.generation
    def fail(*args): raise OSError('synthetic settings failure')
    monkeypatch.setattr(voice_config,'atomic_write_text',fail)
    with pytest.raises(OSError): scott_voice.set_current_voice('scott-voice',acceleration=True)
    assert not voice_config.get_scott_acceleration() and not integrated.engine.config.rms_norm
    assert integrated.engine.generation==generation
