"""The sole voice never loads or falls back to retired speech providers."""
import asyncio
import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import scott_voice as tts
import voice_config
from scott_voice_process import VoiceProcessError

pytestmark = pytest.mark.unit
RETIRED = ('aidar', 'eugene', 'ru-RU-DmitryNeural', 'ru-RU-SvetlanaNeural',
           'en-US-AndrewMultilingualNeural', 'en-US-BrianMultilingualNeural',
           'en-AU-WilliamMultilingualNeural', 'de-DE-FlorianMultilingualNeural')


@pytest.mark.parametrize('old_voice', RETIRED)
def test_old_settings_resolve_to_scott_without_rewriting(old_voice):
    original = json.dumps({'voice': old_voice, 'fallback_voice': old_voice,
                           'scott_profile': 'scott'}).encode()
    voice_config.CONFIG_PATH.write_bytes(original)
    assert tts.get_current_voice() == 'scott-voice'
    assert not tts.set_current_voice(old_voice)
    assert voice_config.CONFIG_PATH.read_bytes() == original


def test_default_ignores_legacy_environment_and_has_approved_profile(monkeypatch):
    monkeypatch.setenv('TTS_ENGINE', 'edge')
    monkeypatch.setenv('TTS_VOICE', 'ru-RU-DmitryNeural')
    module = runpy.run_path(tts.__file__)
    assert module['DEFAULT_VOICE'] == 'scott-voice'
    assert set(module['AVAILABLE_VOICES']) == {'scott-voice'}
    assert voice_config.get_scott_profile() == 'scott'
    assert not voice_config.CONFIG_PATH.exists()


def test_facade_never_initializes_system_or_cloud_engines(monkeypatch, tmp_path):
    import storage_paths
    class Forbidden:
        def __getattr__(self, name):
            pytest.fail('Retired provider accessed: ' + name)
    for name in ('pyttsx3', 'edge_tts', 'silero_tts'):
        monkeypatch.setitem(sys.modules, name, Forbidden())
    monkeypatch.setattr(storage_paths, 'audio_cache', lambda: tmp_path)
    module = runpy.run_path(tts.__file__)
    voice = module['ScottVoice']()
    assert not hasattr(voice, 'tts_thread')


@pytest.mark.parametrize('code', ['not_installed', 'timeout', 'synthesis_failed', 'cancelled'])
def test_scott_failure_never_returns_cached_foreign_audio(tmp_path, monkeypatch, code):
    old = tmp_path / 'scott_foreign.wav'
    old.write_bytes(b'old foreign audio')
    def synthesize(*args):
        raise VoiceProcessError(code)
    monkeypatch.setattr(tts.scott_voice_engine, 'get_engine', lambda: SimpleNamespace(
        generation=1, synthesize=synthesize))
    voice = tts.ScottVoice.__new__(tts.ScottVoice)
    voice.audio_dir = tmp_path
    assert voice.speak_to_file('Синтетическая проверка.') is None
    assert old.read_bytes() == b'old foreign audio'
    assert list(tmp_path.iterdir()) == [old]


@pytest.mark.parametrize('old_voice', RETIRED)
def test_api_rejects_retired_voice_before_synthesis(main_module, monkeypatch, old_voice):
    monkeypatch.setattr(main_module.scott_ai, 'scott_voice', SimpleNamespace(
        speak_to_file=lambda *a, **kw: pytest.fail('Retired voice reached synthesis')))
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main_module.app), base_url='http://localhost') as client:
            for path in ('/voice/select', '/text_to_speech'):
                assert (await client.post(path, json={'voice': old_voice, 'text': 'Проверка.'})).status_code == 400
    asyncio.run(check())


def test_tts_uninstalled_returns_actionable_status_without_synthesis(main_module, monkeypatch):
    monkeypatch.setattr(tts.scott_voice_engine, 'get_engine', lambda: SimpleNamespace(
        describe=lambda: dict(available=False, error='not_installed', reason='Установите Scott Voice в настройках голоса.')))
    monkeypatch.setattr(main_module.scott_ai, 'scott_voice', SimpleNamespace(
        speak_to_file=lambda *a, **kw: pytest.fail('Unavailable voice reached synthesis')))
    response = asyncio.run(main_module.text_to_speech({'text': 'Проверка.'}))
    assert response.status_code == 503
    assert 'Scott Voice' in json.loads(response.body)['error']


def test_preparation_does_not_download_unused_voice(monkeypatch, tmp_path):
    import model_setup
    import recognition_models
    monkeypatch.setattr(model_setup, 'load_environment', lambda: None)
    monkeypatch.setattr(recognition_models, 'selected_engine', lambda: 'openai')
    target = tmp_path / 'speech.pt'
    monkeypatch.setattr(model_setup, 'whisper_spec', lambda: (target, 'https://example.invalid/model', 'sha'))
    downloads = []
    monkeypatch.setattr(model_setup, 'download_file', lambda url, *a, **kw: downloads.append(url))
    monkeypatch.setattr(model_setup, 'models_ready', lambda: True)
    events = []
    model_setup.prepare_models(lambda *event: events.append(event))
    assert downloads == ['https://example.invalid/model']
    assert not any('Silero' in str(event) for event in events)
