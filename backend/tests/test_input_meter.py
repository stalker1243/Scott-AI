"""Visual input telemetry uses synthetic PCM; never opens an audio device."""
import asyncio
import threading
import time
import numpy as np
import pytest

pytestmark = pytest.mark.unit


def test_segment_meter_follows_input_and_expires():
    import listener
    heard = []
    instance = listener.VoiceListener(lambda _: '', heard.append)
    assert instance.input_level() == 0
    instance._running = True
    worker = threading.Thread(target=instance._segment_loop)
    worker.start()
    try:
        instance.feed(np.full(listener.BLOCK_SIZE * 2, .2, dtype=np.float32))
        deadline = time.monotonic() + 1
        while instance.input_level() == 0 and time.monotonic() < deadline:
            time.sleep(.005)
        assert 0 < instance.input_level() <= 1
        instance._suspended = True
        assert instance.input_level() == 0
        instance._suspended = False
        instance._meter = (.8, time.monotonic() - 1)
        assert instance.input_level() == 0
        instance._meter = (.8, time.monotonic())
        instance._running = False
        assert instance.input_level() == 0
        assert heard == []
    finally:
        instance._running = False
        worker.join(2)
    assert not worker.is_alive()


def test_level_endpoint_has_no_recording_or_transcript(monkeypatch):
    import listen_endpoints as endpoints
    from types import SimpleNamespace
    monkeypatch.setattr(endpoints.scott_runtime, 'listener', None)
    assert asyncio.run(endpoints.input_level()) == {'listening': False, 'level': 0}
    monkeypatch.setattr(endpoints.scott_runtime, 'listener', SimpleNamespace(
        is_running=True, input_level=lambda: .67))
    assert asyncio.run(endpoints.input_level()) == {'listening': True, 'level': .67}


def test_protocol_store_is_not_loaded_by_the_application():
    import runtime
    import abilities
    assert runtime.protocols is None
    assert all(item['id'] != 'protocols' for group in abilities.describe()['groups'] for item in group['items'])


@pytest.mark.parametrize('entry,args', [('start_by_id', ('missing',)), ('run_protocol', ('missing',))])
def test_retired_protocols_cannot_execute(monkeypatch, entry, args):
    import protocol_endpoints as endpoints
    monkeypatch.setattr(endpoints.scott_runtime, 'protocols', None)
    def forbidden(*_):
        raise AssertionError('A retired protocol must never run')
    monkeypatch.setattr(endpoints.scott_runtime, 'run_protocol', forbidden)
    result = asyncio.run(getattr(endpoints, entry)(*args))
    assert result['success'] is False
    assert 'отключена' in result['error']
