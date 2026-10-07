"""Exercise the real playback queue with fake devices; never open speakers/mic."""
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.io import wavfile

import speech_player
import echo_reference
import voice_config
from test_scott_voice_engine import integrated
from test_voice_streaming import sink

pytestmark = pytest.mark.unit


class Device:
    def __init__(self):
        self.streams = []
        self.events = []
        self.failure = None
        self.block = None
        self.entered = threading.Event()
        self.release = threading.Event()
        self.abort_releases = True
        self.ignore_aborted_write = False
        self.underflow = False
        self.before_open = None

    def OutputStream(self, **options):
        if self.before_open:
            self.before_open()
        if self.failure == 'open':
            raise RuntimeError('fake open failure')
        device = self

        class Stream:
            aborted = False

            def __init__(self):
                self.options = options
                self.pcm = []
                self.closes = 0
                self.stops = 0
                self.aborts = 0

            def action(self, operation):
                device.events.append(operation)
                if operation == device.block:
                    device.entered.set()
                    assert device.release.wait(3), 'fake device was not released'
                if self.aborted and operation == 'write' and not device.ignore_aborted_write:
                    raise RuntimeError('fake write interrupted')
                if operation == device.failure:
                    raise RuntimeError('fake '+operation+' failure')

            def start(self):
                self.action('start')

            def write(self, pcm):
                self.action('write')
                assert pcm.dtype == np.float32 and pcm.flags.c_contiguous
                self.pcm.append(pcm.copy())
                return device.underflow

            def stop(self):
                self.stops += 1
                self.action('stop')

            def abort(self):
                self.aborts += 1
                self.aborted = True
                device.events.append('abort')
                if device.abort_releases:
                    device.release.set()

            def close(self):
                self.closes += 1
                self.action('close')

        stream = Stream()
        self.streams.append(stream)
        self.events.append('open')
        return stream

    def stop(self):
        self.events.append('legacy_stop')

    def play(self, data, rate, **options):
        self.events.append('legacy_play')

    def wait(self):
        self.events.append('legacy_wait')


@pytest.fixture
def output(monkeypatch, tmp_path):
    device = Device()
    monkeypatch.setattr(speech_player, 'PLAYBACK_AVAILABLE', True)
    monkeypatch.setattr(speech_player, 'sd', device)
    monkeypatch.setattr(speech_player, '_muted', lambda: False)
    monkeypatch.setattr(speech_player, '_volume', lambda: .5)
    monkeypatch.setattr(speech_player, '_output_device', lambda: 7)
    reference = echo_reference.EchoReference()
    monkeypatch.setattr(speech_player.SpeechPlayer, '_echo_reference', staticmethod(lambda: reference))
    player = speech_player.SpeechPlayer()
    paths = []
    for i in range(3):
        path = tmp_path / f'{i}.wav'
        wavfile.write(path, 24000, np.arange(2400, dtype=np.int16)+(i+1)*1000)
        paths.append(str(path))
    yield player, device, reference, paths
    device.release.set()
    player.stop()
    if player._worker:
        player._queue.put(None)
        player._worker.join(3)
        assert not player._worker.is_alive(), 'playback worker leaked'
    assert all(s.closes == 1 for s in device.streams)


def call_in_thread(fn):
    result = []
    def run():
        try:
            result.append(fn())
        except Exception as error:
            result.append(error)
    thread = threading.Thread(target=run)
    thread.start()
    return thread, result


def test_one_device_stream_preserves_pcm_volume_order_and_final_drain(output):
    player, device, ref, paths = output
    token = object()
    for path in paths[:-1]:
        assert player.play_stream(path, token)
    assert player.play_stream(paths[-1], token, last=True, timeout=3)
    assert len(device.streams) == 1
    stream = device.streams[0]
    assert stream.options == dict(samplerate=24000, channels=1, dtype='float32', device=7)
    expected = np.concatenate([wavfile.read(p)[1].astype(np.float32)/32768*.5 for p in paths])
    np.testing.assert_array_equal(np.concatenate(stream.pcm), expected)
    assert stream.stops == stream.closes == 1 and stream.aborts == 0
    assert not player.busy and not ref.playing
    assert player.stream_stats == dict(opened=1, blocks=3, underflows=0)


@pytest.mark.parametrize('frames', [1, 2400, 2401, 4817, 120000])
def test_long_block_uses_bounded_writes_with_exact_pcm_and_one_echo_block(output, frames):
    player, device, ref, paths = output
    samples = np.arange(frames, dtype=np.int32).astype(np.int16)
    wavfile.write(paths[0], 24000, samples)
    blocks = []
    original = ref.stream_block
    def capture(data, rate, at):
        blocks.append((data.copy(), rate, at))
        original(data, rate, at)
    ref.stream_block = capture
    device.underflow = True
    assert player.play_stream(paths[0], object(), last=True, timeout=3)
    stream = device.streams[0]
    assert len(stream.pcm) == (frames+2399)//2400
    assert all(0 < len(p) <= 2400 for p in stream.pcm)
    expected = samples.astype(np.float32)/32768*.5
    np.testing.assert_array_equal(np.concatenate(stream.pcm), expected)
    assert len(blocks) == 1
    np.testing.assert_array_equal(blocks[0][0], expected)
    assert player.stream_stats == dict(opened=1, blocks=1, underflows=1)


def test_abort_that_does_not_interrupt_write_drops_remaining_slices(output):
    player, device, _, paths = output
    wavfile.write(paths[0], 24000, np.full(120000, 1234, dtype=np.int16))
    device.block = 'write'
    device.abort_releases = False
    device.ignore_aborted_write = True
    done = player.queue_stream(paths[0], object(), last=True)
    assert device.entered.wait(2)
    tail = player.queue_stream(paths[1], object(), last=True)
    player.stop()
    assert done.result(1) is False and not done.released.is_set()
    assert tail.result(1) is False and tail.released.is_set()
    device.release.set()
    assert done.released.wait(2)
    assert done.error is None
    assert len(device.streams[0].pcm) == 1
    assert len(device.streams[0].pcm[0]) == 2400
    device.block = None
    assert player.play_stream(paths[2], object(), last=True, timeout=3)
    assert len(device.streams) == 2
    assert device.streams[0].closes == 1


def test_changed_token_and_legacy_audio_are_serialized(output):
    player, device, _, paths = output
    assert player.play_stream(paths[0], object())
    assert player.play_stream(paths[1], object(), last=True, timeout=3)
    assert len(device.streams) == 2
    assert device.events[:9] == ['open','start','write','stop','close','open','start','write','stop']
    device.events.clear()
    player.play_stream(paths[0], object())
    assert player.play_and_wait(paths[1], timeout=3)
    assert device.events == ['open','start','write','stop','close','legacy_play','legacy_wait']


@pytest.mark.parametrize('blocked', ['write', 'stop'])
def test_stop_interrupts_write_or_drain_and_next_response_uses_new_stream(output, blocked):
    player, device, ref, paths = output
    device.block = blocked
    token = object()
    thread, result = call_in_thread(lambda: player.play_stream(paths[0], token, last=True, timeout=3))
    assert device.entered.wait(2)
    old_generation = player.generation
    player.stop()
    thread.join(2)
    assert result == [False]
    assert not player.play_stream(paths[1], token, last=True, generation=old_generation)
    device.block = None
    assert player.play_stream(paths[2], object(), last=True, timeout=3)
    assert len(device.streams) == 2
    assert device.streams[0].closes == 1
    np.testing.assert_array_equal(device.streams[1].pcm[0], wavfile.read(paths[2])[1]/32768*.5)
    assert not ref.playing


def test_repeated_stop_keeps_cleanup_and_drops_queued_tail(output):
    player, device, _, paths = output
    device.block = 'write'
    device.abort_releases = False
    token = object()
    player.play_stream(paths[0], token)
    assert device.entered.wait(2)
    thread, result = call_in_thread(lambda: player.play_stream(paths[1], token, last=True, timeout=3))
    # Wait until the tail is queued; it must be cancelled without playing.
    deadline = time.monotonic()+2
    while player._queue.empty() and time.monotonic() < deadline:
        threading.Event().wait(.005)
    assert not player._queue.empty()
    player.stop()
    player.stop()
    device.release.set()
    thread.join(2)
    assert result == [False]
    device.block = None
    assert player.play_and_wait(paths[2], timeout=3)
    assert len(device.streams) == 1 and device.streams[0].closes == 1
    assert not device.streams[0].pcm


@pytest.mark.parametrize('failure', ['open','start','write','stop','close'])
def test_device_error_releases_waiter_and_closes_handle(output, failure):
    player, device, ref, paths = output
    device.failure = failure
    with pytest.raises(RuntimeError):
        player.play_stream(paths[0], object(), last=True, timeout=3)
    device.failure = None
    assert player.play_and_wait(paths[1], timeout=3)
    assert all(s.closes == 1 for s in device.streams)
    assert not ref.playing


def test_cancel_while_opening_does_not_start_stale_device(output):
    player, device, _, paths = output
    def opening():
        device.entered.set()
        assert device.release.wait(3)
    device.before_open = opening
    thread, result = call_in_thread(lambda: player.play_stream(paths[0], object(), last=True, timeout=3))
    assert device.entered.wait(2)
    player.stop()
    device.release.set()
    thread.join(2)
    assert result == [False]
    device.before_open = None
    assert player.play_and_wait(paths[1], timeout=3)
    assert 'start' not in device.events and 'write' not in device.events


def test_timeout_aborts_stream_and_releases_worker(output):
    player, device, _, paths = output
    device.block = 'write'
    with pytest.raises(TimeoutError):
        player.play_stream(paths[0], object(), last=True, timeout=.1)
    device.block = None
    assert player.play_and_wait(paths[1], timeout=3)
    assert device.streams[0].closes == 1


def test_quiet_force_stale_generation_underflows_and_optional_echo(output, monkeypatch):
    player, device, _, paths = output
    monkeypatch.setattr(speech_player, '_muted', lambda: True)
    assert not player.play_stream(paths[0], object(), last=True)
    player.stop()
    assert not player.play_stream(paths[0], object(), last=True, force=True, generation=0)
    def unavailable():
        raise RuntimeError('fake echo unavailable')
    monkeypatch.setattr(player, '_echo_reference', unavailable)
    device.underflow = True
    assert player.play_stream(paths[0], object(), last=True, force=True, timeout=3)
    assert player.stream_stats == dict(opened=1, blocks=1, underflows=1)
    snapshot = player.stream_stats
    snapshot['opened'] = 999
    assert player.stream_stats['opened'] == 1


@pytest.mark.parametrize('mode,count', [('immediate',3),('2s',2),('complete',0)])
def test_voice_sink_uses_one_token_and_keeps_whole_phrase_file_path(sink, tmp_path, mode, count):
    integrated, player = sink
    voice_config.save_voice('scott-voice', buffer_mode=mode)
    paths = []
    for i in range(3):
        path = tmp_path / f'{i}.wav'
        wavfile.write(path, 24000, np.full(24000, i+1, dtype=np.int16))
        paths.append(str(path))
    calls = []
    def play(path, token, **options):
        calls.append((path,token,options))
        assert wavfile.read(path)[0] == 24000
        return True
    player.play_stream = play
    def stream(text, profile, output, abort):
        for i,path in enumerate(paths):
            output(SimpleNamespace(path=path,seconds=1.), i==2)
        return SimpleNamespace(path=paths[-1])
    integrated.clients[0].stream = stream
    assert integrated.voice.speak_stream('проверка') == paths[-1]
    assert len(calls) == count
    if count:
        assert all(c[1] is calls[0][1] for c in calls)
        assert [c[2]['last'] for c in calls] == [False]*(count-1)+[True]
        assert all(c[2]['generation'] == 0 and not c[2]['force'] for c in calls)
    else:
        assert len(player.calls) == 1 and player.calls[0][1] is True


@pytest.fixture
def reference(monkeypatch):
    clock = [100.]
    monkeypatch.setattr(echo_reference.time, 'monotonic', lambda: clock[0])
    ref = echo_reference.EchoReference()
    ref.start_stream()
    return ref, clock


def test_echo_window_crosses_blocks_and_preserves_real_gap(reference):
    ref, clock = reference
    ref.stream_block(np.ones(1600),16000,100.)
    ref.stream_block(np.full(1600,2),16000,100.1)
    np.testing.assert_array_equal(ref.window(1600,at=100.15), np.r_[np.ones(800),np.full(800,2)])
    ref.delay = 800
    np.testing.assert_array_equal(ref.window(1600,at=100.2), np.r_[np.ones(800),np.full(800,2)])
    ref.delay = 0
    ref.stream_block(np.full(1600,3),16000,100.3)
    np.testing.assert_array_equal(ref.window(3200,at=100.35), np.r_[np.full(800,2),np.zeros(1600),np.full(800,3)])
    assert ref.window(800,at=100.275).size == 0


def test_echo_probe_accumulates_across_blocks_without_reset(reference):
    ref, clock = reference
    signal = np.random.default_rng(7).normal(0,.03,20000).astype(np.float32)
    ref.stream_block(signal[:8000],16000,100.)
    ref.learn_delay(signal[:8000])
    assert ref._probe_samples == 8000
    ref.stream_block(signal[8000:],16000,100.5)
    np.testing.assert_array_equal(ref._signal,signal[:16800])
    assert ref.learn_delay(signal[8000:])
    assert ref.delay == 0 and ref.delay_known
    assert len(ref._signal) == round(echo_reference.LEARN_SECONDS*16000)


def test_echo_history_is_pruned_and_calibration_resets_on_path_change(reference):
    ref, clock = reference
    for i in range(10):
        clock[0] = 100.+i
        ref.stream_block(np.ones(16000),16000,clock[0])
    assert len(ref._segments) <= 5
    assert len(ref._signal) == 16800
    assert ref.window(1600,at=100.1).size == 0
    ref.delay, ref.delay_known = 123, True
    ref.stop()
    ref.start_stream()
    assert ref.delay == 123 and ref.delay_known
    ref.start(np.ones(1600),16000)
    assert ref.delay == 0 and not ref.delay_known and not ref._segments
    ref.delay, ref.delay_known = 123, True
    ref.start_stream()
    assert ref.delay == 0 and not ref.delay_known
