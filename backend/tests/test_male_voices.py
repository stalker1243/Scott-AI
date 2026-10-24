"""Retired female IDs remain rejected after the Scott-only transition.

System voice ranking/worker tests were retired with that implementation;
test_scott_only verifies that no system/cloud/legacy provider is initialized.
"""
import asyncio
import json
import runpy
from types import SimpleNamespace

import httpx
import pytest
import scott_voice as tts
import voice_commands
import voice_config

pytestmark = pytest.mark.unit
RETIRED = ('ru-RU-SvetlanaNeural', 'baya', 'kseniya', 'xenia')


def test_catalog_and_spoken_catalog_only_contain_scott():
    assert tts.AVAILABLE_VOICES == {'scott-voice': 'Scott Voice'}
    assert tts.VOICE_GENDERS == {'scott-voice': 'male'}
    assert set(voice_commands.ALIASES.values()) == {'scott-voice'}
    assert tts.describe_voices('female')['voices'] == []


@pytest.mark.parametrize('retired', RETIRED)
def test_old_choice_resolves_without_rewriting_settings(retired):
    original = json.dumps({'voice':retired, 'fallback_voice':retired, 'scott_profile':'scott'}).encode()
    voice_config.CONFIG_PATH.write_bytes(original)
    assert tts.get_current_voice() == 'scott-voice'
    assert not tts.set_current_voice(retired)
    assert voice_config.CONFIG_PATH.read_bytes() == original


@pytest.mark.parametrize('value', RETIRED)
def test_retired_environment_defaults_cannot_select_female(value, monkeypatch):
    monkeypatch.setenv('SILERO_VOICE', value)
    monkeypatch.setenv('TTS_VOICE', value)
    data = runpy.run_path(tts.__file__)
    assert data['DEFAULT_VOICE'] == 'scott-voice'


@pytest.mark.parametrize('value', (*RETIRED, [], 123, ''))
def test_api_rejects_retired_or_invalid_voice_before_synthesis(main_module, monkeypatch, value):
    fake = SimpleNamespace(speak_to_file=lambda *a, **kw: pytest.fail('Retired voice reached synthesis'))
    monkeypatch.setattr(main_module.scott_ai, 'scott_voice', fake)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main_module.app), base_url='http://localhost') as client:
            for path in ('/voice/select', '/text_to_speech'):
                response = await client.post(path, json={'voice':value, 'text':'Синтетическая проверка.'})
                assert response.status_code == 400
    asyncio.run(check())
