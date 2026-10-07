"""Speech controls use temporary settings and fake playback/OS executors."""
import asyncio
import threading
from types import SimpleNamespace

import httpx
import pytest

import audio_settings
import scott_voice
import speech_player
import understanding
import voice_commands
import voice_config
from command_parser import CommandParser
from fast_intent import get_fast_intent_engine
from question_answerer import get_question_answerer

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def isolated_audio(tmp_path, monkeypatch):
    monkeypatch.setattr(audio_settings, 'CONFIG_PATH', tmp_path / 'audio.json')


@pytest.mark.parametrize('text,action,value', [
    ('Скотт, пожалуйста, выбери голос Светланы', 'select', 'ru-RU-SvetlanaNeural'),
    ('смени голос на Айдара', 'select', 'aidar'),
    ('выбери голос Ксении', 'select', 'kseniya'),
    ('выключи озвучку!', 'quiet', True),
    ('включи озвучку', 'quiet', False),
    ('громкость голоса 50 процентов', 'volume', 50),
    ('установи громкость голоса на 0%', 'volume', 0),
    ('говори громче', 'volume_delta', 10),
    ('говори тише', 'volume_delta', -10),
    ('измени характер голоса на чёткий', 'character', 'clear'),
    ('выбери стиль голоса из динамика', 'character', 'speaker'),
    ('какой голос выбран?', 'status', None),
    ('выключаю звучку', 'quiet', True),
    ('выключу звучку', 'quiet', True),
    ('ключи озвучку', 'quiet', False),
    ('измени характеры голоса на четкий', 'character', 'clear'),
    ('выбери стиль голоса спокойный', 'character', 'calm'),
    ('смени характер голоса на мягкий', 'character', 'calm'),
    ('выбери голос Пайдара', 'select', 'aidar'),
])
def test_voice_command_routing(text, action, value):
    decision = understanding.understand(text, intent_engine=get_fast_intent_engine(),
        parser=CommandParser(), answerer=get_question_answerer())
    assert (decision.kind, decision.action) == ('action', 'voice_settings')
    assert decision.parsed.main_param == action
    assert decision.parsed.context['voice_value'] == value


@pytest.mark.parametrize('text', ['как поменять голос', 'почему ты говоришь тише',
    'выключи компьютер', 'громкость 50', 'убавь звук', 'запомни, что я люблю голос Светланы'])
def test_voice_parser_does_not_capture_unrelated_commands(text):
    assert voice_commands.parse(text) is None


def test_voice_selection_survives_reload():
    assert scott_voice.set_current_voice('ru-RU-SvetlanaNeural')
    assert voice_config.get_voice('aidar', scott_voice.AVAILABLE_VOICES) == 'ru-RU-SvetlanaNeural'
    assert scott_voice.get_current_voice() == 'ru-RU-SvetlanaNeural'
    assert not scott_voice.set_current_voice('unknown')
    assert scott_voice.get_current_voice() == 'ru-RU-SvetlanaNeural'


@pytest.mark.parametrize('content', ['{broken', '[]', '{"voice":"unknown"}', '{"voice":null}'])
def test_corrupt_voice_config_falls_back(content):
    voice_config.CONFIG_PATH.write_text(content, encoding='utf-8')
    assert scott_voice.get_current_voice() == scott_voice.DEFAULT_VOICE


def test_voice_actions_save_without_changing_system_volume(monkeypatch):
    import audio_endpoints
    stopped = []
    monkeypatch.setattr(audio_endpoints, '_stop_current_speech', lambda: stopped.append(True))
    assert 'сохранён' in voice_commands.execute('select', 'baya')
    assert scott_voice.get_current_voice() == 'baya'
    voice_commands.execute('volume', 50)
    voice_commands.execute('volume_delta', -10)
    assert audio_settings.get_settings()['volume'] == 40
    assert '❌' in voice_commands.execute('volume', 101)
    voice_commands.execute('quiet', True)
    assert audio_settings.is_quiet() and stopped == [True]
    voice_commands.execute('quiet', False)
    assert not audio_settings.is_quiet()
    voice_commands.execute('character', 'clear')
    assert audio_settings.get_character() == 'clear'


def test_repeated_action_ignores_cached_acknowledgement(main_module, monkeypatch):
    main = main_module
    calls = []
    monkeypatch.setattr(main, 'HAS_V32_FEATURES', False)
    monkeypatch.setattr(main, 'knowledge_base', SimpleNamespace(
        search_memory=lambda _: {'открой блокнот': {'value': 'старое подтверждение', 'category': 'general'}},
        add_conversation=lambda *args: None))
    monkeypatch.setattr(main.executor, 'execute', lambda *args, **kwargs: calls.append(args) or 'Выполнено')
    for _ in range(2):
        result = asyncio.run(main.scott_ai.process_command('открой блокнот'))
        assert result['type'] == 'command'
    assert len(calls) == 2


def test_main_executes_voice_settings(main_module, monkeypatch):
    main = main_module
    monkeypatch.setattr(main, 'HAS_V32_FEATURES', False)
    monkeypatch.setattr(main, 'knowledge_base', SimpleNamespace(
        search_memory=lambda _: {}, add_conversation=lambda *args: None))
    result = asyncio.run(main.scott_ai.process_command('выбери голос Бая'))
    assert result['type'] == 'command'
    assert scott_voice.get_current_voice() == 'baya'


@pytest.mark.parametrize('body', [{'quiet': 'false'}, {'volume': 101}, {'volume': True},
    {'input_device': []}, {'character': []}, {'character': 'missing'}])
def test_audio_api_rejects_invalid_values(main_module, body):
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main_module.app), base_url='http://test') as client:
            response = await client.post('/audio/settings', json=body)
            assert response.status_code == 400
            assert not response.json()['success']
    asyncio.run(check())
    assert not audio_settings.CONFIG_PATH.exists()


def test_voice_api_catalog_and_saved_selection(main_module):
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main_module.app), base_url='http://test') as client:
            catalog = (await client.get('/voice/available')).json()
            assert len([v for v in catalog['voices'] if v['engine'] == 'silero']) == 5
            optional = next(v for v in catalog['voices'] if v['id'] == 'scott-voice')
            assert optional['local'] and optional['engine'] == 'qwen' and not optional['available']
            assert any(v['id'] == 'ru-RU-SvetlanaNeural' and v['gender'] == 'female' for v in catalog['voices'])
            assert (await client.post('/voice/select', json={'voice': 123})).status_code == 400
            response = await client.post('/voice/select', json={'voice': 'ru-RU-SvetlanaNeural'})
            assert response.json()['success']
            assert (await client.get('/voice/available')).json()['current'] == 'ru-RU-SvetlanaNeural'
    asyncio.run(check())


def test_failed_voice_save_preserves_previous_choice(main_module, monkeypatch):
    scott_voice.set_current_voice('baya')
    monkeypatch.setattr(voice_config, 'atomic_write_text', lambda *args: (_ for _ in ()).throw(OSError('disk')))
    response = asyncio.run(main_module.select_voice({'voice': 'aidar'}))
    assert response.status_code == 503
    assert scott_voice.get_current_voice() == 'baya'


def test_playback_error_is_reported_to_waiter(monkeypatch):
    player = speech_player.SpeechPlayer()
    monkeypatch.setattr(player, '_play_file', lambda _: (_ for _ in ()).throw(RuntimeError('device lost')))
    with pytest.raises(RuntimeError, match='device lost'):
        player.play_and_wait('fake.wav', timeout=1)


def test_playback_timeout_cancels_wait(monkeypatch):
    player = speech_player.SpeechPlayer()
    release = threading.Event()
    monkeypatch.setattr(player, '_play_file', lambda _: release.wait(1))
    monkeypatch.setattr(speech_player.sd, 'stop', lambda: None)
    try:
        with pytest.raises(TimeoutError):
            player.play_and_wait('fake.wav', timeout=0.02)
    finally:
        release.set()


def test_stop_during_synthesis_does_not_enqueue_later_chunks(monkeypatch):
    player = speech_player.SpeechPlayer()
    monkeypatch.setattr(speech_player, 'get_player', lambda: player)
    monkeypatch.setattr(speech_player.sd, 'stop', lambda: None)
    voice = scott_voice.ScottVoice.__new__(scott_voice.ScottVoice)
    played = []
    monkeypatch.setattr(voice, 'speak_to_file', lambda _: player.stop() or 'fake.wav')
    monkeypatch.setattr(voice, 'play_audio', lambda *a, **k: played.append(a))
    assert voice.speak('Готово.') is None
    assert played == []


def test_speak_api_does_not_report_success_for_failed_audio(main_module, monkeypatch):
    monkeypatch.setattr(main_module, 'scott_voice', SimpleNamespace(speak=lambda *args: None))
    assert not asyncio.run(main_module.speak_text('Тест', False))['success']


def test_stale_playback_cannot_enter_queue_after_stop(monkeypatch):
    player = speech_player.SpeechPlayer()
    monkeypatch.setattr(speech_player.sd, 'stop', lambda: None)
    generation = player.generation
    player.stop()
    assert not player.play('fake.wav', generation=generation)
    assert not player.play_and_wait('fake.wav', generation=generation)
    assert not player.busy


def test_stop_during_mp3_conversion_prevents_replay(tmp_path, monkeypatch):
    import sys
    player = speech_player.SpeechPlayer()
    monkeypatch.setattr(speech_player, 'get_player', lambda: player)
    monkeypatch.setattr(speech_player.sd, 'stop', lambda: None)
    class Sound:
        def export(self, path, **kwargs):
            from pathlib import Path
            Path(path).write_bytes(b'fake wav')
            player.stop()
    monkeypatch.setitem(sys.modules, 'pydub', SimpleNamespace(AudioSegment=SimpleNamespace(from_mp3=lambda _: Sound())))
    voice = scott_voice.ScottVoice.__new__(scott_voice.ScottVoice)
    voice.audio_dir = tmp_path
    assert not voice.play_audio(str(tmp_path / 'fake.mp3'))
    assert not player.busy


def test_async_speech_wrapper_does_not_play_twice():
    wrapper = scott_voice.ScottVoiceAsync.__new__(scott_voice.ScottVoiceAsync)
    calls = []
    wrapper.voice = SimpleNamespace(speak=lambda text: calls.append(text) or 'fake.wav',
        play_audio=lambda _: pytest.fail('speak already plays the file'))
    assert asyncio.run(wrapper.speak_and_play('Тест')) == 'fake.wav'
    assert calls == ['Тест']


def test_error_from_cancelled_audio_does_not_cancel_new_response(monkeypatch):
    player = speech_player.SpeechPlayer()
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    monkeypatch.setattr(speech_player.sd, 'stop', lambda: None)
    def play(path):
        if path == 'old.wav':
            started.set()
            release.wait(1)
            raise RuntimeError('old device error')
        finished.set()
    monkeypatch.setattr(player, '_play_file', play)
    player.play('old.wav')
    assert started.wait(1)
    player.stop()
    player.play('new.wav')
    release.set()
    assert finished.wait(1)
