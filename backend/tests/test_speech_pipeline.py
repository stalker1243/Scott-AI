"""Next-phrase preparation, ownership and cancellation with fake audio only."""
import asyncio
from pathlib import Path
import threading
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.io import wavfile

import audio_settings
import speech_player
import voice_config
from scott_voice_process import VoiceProcessError
from speech_pipeline import QueuedSpeech
from test_stream_playback import output, call_in_thread
from test_scott_voice_engine import integrated

pytestmark = pytest.mark.unit


@pytest.fixture
def pipeline(output, integrated, monkeypatch, tmp_path):
    player,device,reference,paths = output
    monkeypatch.setattr(speech_player,'get_player',lambda:player)
    monkeypatch.setattr(audio_settings,'is_quiet',lambda:False)
    voice_config.save_voice('scott-voice',streaming=True,buffer_mode='immediate')
    integrated.engine.synthesize('init')
    requests = []
    second = threading.Event()
    custom = [None]
    def stream(text,profile,on_audio,on_abort):
        requests.append(text)
        if custom[0] is not None:
            custom[0](text,on_audio)
        else:
            temporary = []
            for i in range(2):
                path = tmp_path/f'{text}-{i}.wav'
                wavfile.write(path,24000,np.full(2400,len(requests)*1000+i,dtype=np.int16))
                on_audio(SimpleNamespace(path=str(path),seconds=.1,cached=False),i==1)
                temporary.append(path)
            # The process client removes all blocks after the last callback.
            for path in temporary:
                path.unlink()
        full = tmp_path/f'full-{text}.wav'
        wavfile.write(full,24000,np.zeros(4800,dtype=np.int16))
        if len(requests)==2:
            second.set()
        return SimpleNamespace(path=str(full))
    integrated.clients[0].stream = stream
    yield SimpleNamespace(voice=integrated.voice,engine=integrated.engine,player=player,
        device=device,reference=reference,paths=paths,requests=requests,second=second,
        custom=custom,root=tmp_path)


def folders(state):
    return list(state.root.glob('.scott-prefetch-*'))


def test_next_phrase_starts_before_current_drain_but_third_waits(pipeline):
    state = pipeline
    state.device.block = 'stop'
    thread,result = call_in_thread(lambda:state.voice.speak_stream_parts(['первая','вторая','третья']))
    assert state.device.entered.wait(2)
    assert state.second.wait(2), 'next synthesis waited for current playback'
    assert state.requests == ['первая','вторая']
    assert folders(state) and thread.is_alive()
    assert not list(state.root.glob('первая-*.wav'))
    state.device.release.set()
    thread.join(3)
    assert result == [str(state.root/'full-первая.wav')]
    assert state.requests == ['первая','вторая','третья']
    assert len(state.device.streams)==3 and not folders(state)
    expected = np.concatenate([np.full(2400,n*1000+i,dtype=np.float32)/32768*.5
        for n in range(1,4) for i in range(2)])
    actual = np.concatenate([pcm for stream in state.device.streams for pcm in stream.pcm])
    np.testing.assert_array_equal(actual,expected)
    assert not state.reference.playing


def test_stop_keeps_active_copy_until_write_exits_and_drops_all_prefetched_audio(pipeline):
    state = pipeline
    state.device.block = 'write'
    state.device.abort_releases = False
    thread,result = call_in_thread(lambda:state.voice.speak_stream_parts(['первая','вторая','третья']))
    assert state.device.entered.wait(2)
    assert state.second.wait(2)
    state.player.stop()
    state.player.stop()
    thread.join(2)
    assert result == [None]
    remaining = folders(state)
    assert len(remaining)==1 and len(list(remaining[0].glob('*.wav')))==1
    state.device.release.set()
    state.device.block = None
    assert state.player.play_and_wait(state.paths[0],timeout=3)
    assert not folders(state)
    assert state.requests == ['первая','вторая']
    assert not state.device.streams[0].pcm


@pytest.mark.parametrize('cause',['caller','quiet','engine'])
def test_cancellation_while_waiting_does_not_play_queued_continuation(pipeline,monkeypatch,cause):
    state = pipeline
    cancelled = threading.Event()
    quiet = [False]
    monkeypatch.setattr(audio_settings,'is_quiet',lambda:quiet[0])
    state.device.block = 'stop'
    thread,result = call_in_thread(lambda:state.voice.speak_stream_parts(['первая','вторая','третья'],
        cancelled=cancelled.is_set))
    assert state.device.entered.wait(2) and state.second.wait(2)
    if cause=='caller':
        cancelled.set()
    elif cause=='quiet':
        quiet[0] = True
    else:
        state.engine.cancel()
    thread.join(2)
    assert result == [None]
    state.device.block = None
    assert state.player.play_and_wait(state.paths[0],force=True,timeout=3)
    assert not folders(state) and len(state.device.streams)==1


@pytest.mark.parametrize('mode',['2s','4s','complete'])
def test_whole_buffer_or_short_phrase_can_prepare_next_without_native_stream(pipeline,mode):
    state = pipeline
    voice_config.save_voice('scott-voice',buffer_mode=mode)
    entered,release = threading.Event(),threading.Event()
    def wait():
        entered.set()
        assert release.wait(3)
    state.device.wait = wait
    thread,result = call_in_thread(lambda:state.voice.speak_stream_parts(['первая','вторая','третья']))
    try:
        assert entered.wait(2) and state.second.wait(2)
        assert state.requests == ['первая','вторая']
    finally:
        release.set()
    thread.join(3)
    assert result == [str(state.root/'full-первая.wav')]
    assert not state.device.streams and not folders(state)


def test_error_in_prefetched_phrase_never_replays_its_partial_output(pipeline,monkeypatch):
    state = pipeline
    state.device.block = 'stop'
    def stream(text,on_audio):
        on_audio(SimpleNamespace(path=state.paths[0],seconds=.1),False)
        if text=='вторая':
            raise VoiceProcessError('synthesis_failed')
        on_audio(SimpleNamespace(path=state.paths[1],seconds=.1),True)
    state.custom[0] = stream
    monkeypatch.setattr(state.voice,'_speak_to_file_locked',lambda *args:pytest.fail('partial output repeated'))
    assert state.voice.speak_stream_parts(['первая','вторая','третья']) is None
    state.device.block = None
    assert state.player.play_and_wait(state.paths[0],timeout=3)
    assert state.requests == ['первая','вторая'] and not folders(state)


def test_failure_before_first_audio_can_queue_fallback_once(pipeline,monkeypatch):
    state = pipeline
    state.custom[0] = lambda *args:(_ for _ in ()).throw(VoiceProcessError('stream_unavailable'))
    fallback = []
    monkeypatch.setattr(state.voice,'_speak_to_file_locked',lambda *args:fallback.append(args[0]) or state.paths[0])
    assert state.voice.speak_stream_parts(['первая']) == state.paths[0]
    assert fallback == ['первая'] and not state.device.streams and not folders(state)
    assert state.device.events.count('legacy_play')==1


def test_cached_whole_phrase_is_copied_before_source_disappears(pipeline):
    state = pipeline
    def cached(text,on_audio):
        path = state.root/f'cached-{text}.wav'
        wavfile.write(path,24000,np.full(4800,1234,dtype=np.int16))
        on_audio(SimpleNamespace(path=str(path),seconds=.2,cached=True),True)
        path.unlink()
    state.custom[0] = cached
    assert state.voice.speak_stream_parts(['первая','вторая'])
    assert state.device.events.count('legacy_play')==2 and not state.device.streams
    assert not folders(state)


def test_copy_failure_cleans_partial_owned_file_without_fallback_or_audio(pipeline,monkeypatch):
    import speech_pipeline
    def copy(source,destination):
        Path(destination).write_bytes(b'partial')
        raise OSError('synthetic copy failure')
    monkeypatch.setattr(speech_pipeline.shutil,'copyfile',copy)
    monkeypatch.setattr(pipeline.voice,'_speak_to_file_locked',lambda *args:pytest.fail('failed copy replayed'))
    assert pipeline.voice.speak_stream_parts(['первая']) is None
    assert not pipeline.device.streams and not folders(pipeline)


def test_force_preview_bypasses_quiet_but_regular_pipeline_does_not(pipeline,monkeypatch):
    state = pipeline
    monkeypatch.setattr(audio_settings,'is_quiet',lambda:True)
    assert state.voice.speak_stream_parts(['первая']) is None
    assert not state.requests
    assert state.voice.speak_stream_parts(['первая'],force=True)
    assert state.requests == ['первая'] and not folders(state)


def test_playback_receipt_cleanup_runs_after_write_and_outside_player_lock(output):
    player,device,_,paths = output
    device.block = 'write'
    device.abort_releases = False
    released = []
    def cleanup():
        released.append(player.generation)  # Acquires player lock: cannot deadlock.
    ticket = player.queue_stream(paths[0],object(),last=True,on_finished=cleanup)
    assert device.entered.wait(2)
    player.stop()
    assert ticket.result(0) is False
    assert not ticket.released.is_set() and not released
    device.release.set()
    assert ticket.released.wait(2)
    assert released == [1]


def test_cleanup_exception_does_not_kill_worker_or_block_following_job(output):
    player,device,_,paths = output
    def cleanup():
        raise RuntimeError('synthetic cleanup failure')
    receipt = player.queue_file(paths[0],on_finished=cleanup)
    assert receipt.result(3) and receipt.released.is_set()
    assert player.play_and_wait(paths[1],timeout=3)


def test_owned_copies_are_released_when_stale_enqueue_is_rejected(output,tmp_path):
    player,_,_,paths = output
    owner = QueuedSpeech(player,0)
    player.stop()
    with pytest.raises(VoiceProcessError,match='cancelled'):
        owner.submit([paths[0]],True,False)
    owner.seal()
    assert not list(tmp_path.glob('.scott-prefetch-*'))


@pytest.mark.parametrize('invalid',[None,'phrase',[''],[7]])
def test_invalid_pipeline_input_cannot_create_jobs(pipeline,invalid):
    with pytest.raises(ValueError):
        pipeline.voice.speak_stream_parts(invalid)
    assert not pipeline.requests


@pytest.mark.parametrize('cancel',[False,True])
def test_api_voice_reply_uses_pipeline_and_keeps_echo_until_all_audio_finishes(main_module,monkeypatch,cancel):
    import runtime
    voice_config.save_voice('scott-voice',streaming=True)
    monkeypatch.setattr(audio_settings,'is_quiet',lambda:False)
    text = 'Проверка всех слов при подготовке следующей части. '*10
    spoken,echo = [],[]
    def parts(chunks,cancelled):
        assert echo==['start'] and not cancelled()
        spoken.extend(chunks)
        if cancel:
            main_module._next_voice_response()
        assert cancelled() is cancel
        return 'synthetic-complete.wav'
    def duplicate(*args,**options):
        pytest.fail('pipeline reply was repeated')
    monkeypatch.setattr(runtime,'scott_voice',SimpleNamespace(speak_stream_parts=parts,
        speak_stream=duplicate,speak_to_file=duplicate,play_audio=duplicate))
    monkeypatch.setattr(runtime,'listener',SimpleNamespace(expect_interruption=lambda _:echo.append('start'),
        stop_expecting=lambda:echo.append('stop')))
    generation = main_module._next_voice_response()
    assert asyncio.run(main_module._play_voice_response(text,generation)) is (not cancel)
    assert ' '.join(spoken).split()==text.split() and echo==['start','stop']


def test_direct_speak_routes_streaming_parts_through_pipeline(pipeline,monkeypatch):
    calls = []
    def parts(parts,force=False,cancelled=None):
        assert not cancelled()
        calls.append((parts,force))
        return 'first.wav'
    monkeypatch.setattr(pipeline.voice,'speak_stream_parts',parts)
    text = 'Проверка подготовки следующей части. '*12
    assert pipeline.voice.speak(text,force=True)=='first.wav'
    assert ' '.join(calls[0][0]).split()==text.split() and calls[0][1] is True


def test_direct_speak_keeps_generation_captured_before_preparing_chunks(pipeline,monkeypatch):
    import scott_voice_engine
    def chunks(*args,**options):
        pipeline.player.stop()
        return ['отменённый ответ']
    monkeypatch.setattr(scott_voice_engine,'speech_chunks',chunks)
    assert pipeline.voice.speak('отменённый ответ') is None
    assert not pipeline.requests and not folders(pipeline)


def test_cancelled_async_reply_signals_background_pipeline(main_module,monkeypatch):
    import runtime
    voice_config.save_voice('scott-voice',streaming=True)
    monkeypatch.setattr(audio_settings,'is_quiet',lambda:False)
    started,finished = threading.Event(),threading.Event()
    echo = []
    def parts(chunks,cancelled):
        started.set()
        deadline = __import__('time').monotonic()+3
        while not cancelled() and __import__('time').monotonic()<deadline:
            threading.Event().wait(.01)
        assert cancelled(), 'abandoned coroutine left its pipeline running'
        finished.set()
        return None
    monkeypatch.setattr(runtime,'scott_voice',SimpleNamespace(speak_stream_parts=parts,speak_stream=lambda _:None))
    monkeypatch.setattr(runtime,'listener',SimpleNamespace(expect_interruption=lambda _:echo.append('start'),
        stop_expecting=lambda:echo.append('stop')))
    async def run():
        task = asyncio.create_task(main_module._play_voice_response('Проверка отмены фоновой задачи.'))
        assert await asyncio.to_thread(started.wait,2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await asyncio.to_thread(finished.wait,2)
    asyncio.run(run())
    assert echo==['start','stop']
