"""Buffered speech keeps words, cancellation and pre-output fallback intact."""
from pathlib import Path
from types import SimpleNamespace
import asyncio
import json
import wave

import httpx
import pytest

import voice_config
from speech_buffer import SpeechBuffer, join_wavs
from scott_voice_process import VoiceProcessError
from test_scott_voice_engine import integrated
from test_voice_streaming import sink

pytestmark = pytest.mark.unit


def audio(tmp_path, name, seconds=1., value=b'\x01\x00'):
    path = tmp_path / (name + '.wav')
    with wave.open(str(path), 'wb') as output:
        output.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        output.writeframes(value * round(seconds * 24000))
    return SimpleNamespace(path=str(path), seconds=seconds)


def pcm(path):
    with wave.open(str(path), 'rb') as source:
        return source.readframes(source.getnframes())


@pytest.mark.parametrize('mode,expected', [('immediate', [[0],[1],[2]]), ('2s', [[0,1],[2]]), ('4s', [[0,1,2]]), ('complete', [[0,1,2]])])
def test_release_threshold_and_short_final_phrase(mode, expected):
    buffer = SpeechBuffer(mode)
    released = []
    for index in range(3):
        ready = buffer.push(SimpleNamespace(seconds=1., index=index), index == 2)
        if ready:
            released.append([v.index for v in ready])
    assert released == expected
    with pytest.raises(ValueError):
        buffer.push(SimpleNamespace(seconds=1.), True)


@pytest.mark.parametrize('duration', [0, -1, True, float('nan'), float('inf'), '1'])
def test_invalid_duration_is_rejected_before_playback(duration):
    with pytest.raises(ValueError):
        SpeechBuffer('2s').push(SimpleNamespace(seconds=duration), False)


def test_discard_never_releases_pending_speech():
    buffer = SpeechBuffer('complete')
    assert not buffer.push(SimpleNamespace(seconds=1.), False)
    buffer.discard()
    with pytest.raises(ValueError):
        buffer.push(SimpleNamespace(seconds=1.), True)


def test_pending_blocks_are_bounded():
    buffer = SpeechBuffer('complete')
    for _ in range(128):
        assert not buffer.push(SimpleNamespace(seconds=.1), False)
    with pytest.raises(ValueError):
        buffer.push(SimpleNamespace(seconds=.1), False)


def test_join_keeps_every_pcm_sample_in_order(tmp_path):
    blocks = [audio(tmp_path, 'one', .03), audio(tmp_path, 'two', .02, b'\x02\x00')]
    expected = b''.join(pcm(v.path) for v in blocks)
    path = join_wavs([v.path for v in blocks], tmp_path/'joined.wav')
    assert pcm(path) == expected
    assert [pcm(v.path) for v in blocks] == [expected[:1440], expected[1440:]]


def test_join_rejects_truncated_block(tmp_path):
    block = audio(tmp_path, 'broken', .03)
    path = Path(block.path)
    path.write_bytes(path.read_bytes()[:-2])
    with pytest.raises(ValueError, match='Truncated'):
        join_wavs([path], tmp_path/'joined.wav')


@pytest.mark.parametrize('saved', [None, [], 4, True, 'unknown'])
def test_invalid_saved_preference_uses_immediate_playback(saved):
    voice_config.CONFIG_PATH.write_text(json.dumps({'scott_buffer': saved}))
    assert voice_config.get_scott_buffer() == 'immediate'


def test_buffer_preference_preserves_voice_profile_and_other_choices():
    voice_config.save_voice('eugene')
    voice_config.save_voice('scott-voice', profile='digital', streaming=True, acceleration=True, buffer_mode='4s')
    voice_config.save_voice('eugene')
    voice_config.save_voice('scott-voice')
    assert voice_config.get_scott_buffer() == '4s'
    assert voice_config.get_scott_profile() == 'digital'
    assert voice_config.get_scott_streaming() and voice_config.get_scott_acceleration()
    assert voice_config.get_fallback_voice('demo', ['demo', 'eugene']) == 'eugene'


@pytest.mark.parametrize('mode', ['2s', '4s', 'complete'])
def test_voice_sink_merges_initial_blocks_and_cleans_only_temporary_output(sink, tmp_path, mode):
    integrated, player = sink
    voice_config.save_voice('scott-voice', buffer_mode=mode)
    blocks = [audio(tmp_path, str(i), 1., bytes([i+1, 0])) for i in range(3)]
    received = []
    temporary = []
    def play(path, **options):
        received.append(pcm(path))
        temporary.append(Path(path))
        return True
    player.play = player.play_and_wait = play
    def stream(text, profile, output, abort):
        for index, block in enumerate(blocks):
            output(block, index == 2)
            if index == 0:
                assert not received
        return blocks[-1]
    integrated.clients[0].stream = stream
    assert integrated.voice.speak_stream('проверка') == blocks[-1].path
    assert b''.join(received) == b''.join(pcm(v.path) for v in blocks)
    assert len(received) == (2 if mode == '2s' else 1)
    assert not temporary[0].exists()
    assert all(Path(v.path).is_file() for v in blocks)
    assert not list(tmp_path.glob('.scott-playback-*'))


def test_failure_while_buffering_can_fall_back_before_any_sound(sink, tmp_path, monkeypatch):
    integrated, player = sink
    voice_config.save_voice('scott-voice', buffer_mode='4s')
    block = audio(tmp_path, 'block')
    fallback = audio(tmp_path, 'fallback')
    def stream(text, profile, output, abort):
        output(block, False)
        assert not player.calls
        abort()
        raise VoiceProcessError('synthesis_failed')
    integrated.clients[0].stream = stream
    monkeypatch.setattr(integrated.voice, '_speak_to_file_locked', lambda *args: fallback.path)
    assert integrated.voice.speak_stream('проверка') == fallback.path
    assert player.calls == [(fallback.path, True)]


def test_failure_after_buffer_release_stops_without_replaying(sink, tmp_path, monkeypatch):
    integrated, player = sink
    voice_config.save_voice('scott-voice', buffer_mode='2s')
    blocks = [audio(tmp_path, str(i)) for i in range(2)]
    def stream(text, profile, output, abort):
        for block in blocks:
            output(block, False)
        assert len(player.calls) == 1
        abort()
        raise VoiceProcessError('synthesis_failed')
    integrated.clients[0].stream = stream
    monkeypatch.setattr(integrated.voice, '_speak_to_file_locked', lambda *args: pytest.fail('Partial speech replayed'))
    assert integrated.voice.speak_stream('проверка') is None
    assert len([v for v in player.calls if v[0] != 'stop']) == 1
    assert player.calls[-1] == ('stop', True)
    assert not list(tmp_path.glob('.scott-playback-*'))


@pytest.mark.parametrize('cause', ['engine', 'player', 'quiet'])
def test_interruption_drops_buffer_without_sound_or_fallback(sink, tmp_path, monkeypatch, cause):
    import audio_settings
    integrated, player = sink
    quiet = [False]
    monkeypatch.setattr(audio_settings, 'is_quiet', lambda: quiet[0])
    voice_config.save_voice('scott-voice', buffer_mode='4s')
    block = audio(tmp_path, 'block')
    def stream(text, profile, output, abort):
        output(block, False)
        if cause == 'engine': integrated.engine.cancel()
        elif cause == 'player': player.stop()
        else: quiet[0] = True
        output(block, True)
        pytest.fail('Interrupted buffer continued')
    integrated.clients[0].stream = stream
    monkeypatch.setattr(integrated.voice, '_speak_to_file_locked', lambda *args: pytest.fail('Cancelled speech used fallback'))
    assert integrated.voice.speak_stream('проверка') is None
    assert all(v[0] == 'stop' for v in player.calls)
    assert not list(tmp_path.glob('.scott-playback-*'))


def test_ready_full_cache_is_played_once_without_extra_wait(sink, tmp_path):
    integrated, player = sink
    voice_config.save_voice('scott-voice', buffer_mode='complete')
    block = audio(tmp_path, 'cached', 6.)
    def stream(text, profile, output, abort):
        output(block, True)
        return block
    integrated.clients[0].stream = stream
    assert integrated.voice.speak_stream('проверка') == block.path
    assert player.calls == [(block.path, True)]


def test_api_rejects_unknown_buffer_and_preserves_settings(main_module, integrated):
    voice_config.save_voice('scott-voice', profile='restrained', streaming=True)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main_module.app), base_url='http://test') as client:
            for value in (None, True, 2, 'unknown', [], {}):
                assert (await client.post('/voice/select', json={'voice':'scott-voice', 'buffer':value})).status_code == 400
                assert voice_config.get_scott_buffer() == 'immediate'
            assert (await client.post('/voice/select', json={'voice':'eugene', 'buffer':'4s'})).status_code == 400
            generation = integrated.engine.generation
            assert (await client.post('/voice/select', json={'voice':'scott-voice', 'buffer':'4s'})).status_code == 200
            assert integrated.engine.generation > generation
            catalog = (await client.get('/voice/available')).json()
            assert catalog['scott_buffer'] == '4s' and len(catalog['scott_buffers']) == 4
            assert voice_config.get_scott_profile() == 'restrained' and voice_config.get_scott_streaming()
            assert (await client.post('/voice/select', json={'voice':'scott-voice', 'buffer':'immediate'})).status_code == 200
    asyncio.run(run())
