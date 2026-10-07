"""Uploads own their files; decoding and inference cannot block HTTP health."""

import asyncio
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import audio_uploads

pytestmark = pytest.mark.unit


class Audio:
    dBFS = -12

    def __len__(self):
        return 800

    def apply_gain(self, gain):
        self.gain = gain
        return self

    def export(self, path, **kwargs):
        Path(path).write_bytes(b'normalized')


@pytest.fixture(autouse=True)
def fake_decoder(monkeypatch):
    monkeypatch.setitem(sys.modules, 'pydub', SimpleNamespace(AudioSegment=SimpleNamespace(from_file=lambda _: Audio())))


def test_parallel_uploads_with_same_filename_keep_their_own_contents(main_module, monkeypatch):
    barrier = threading.Barrier(2)
    paths = []
    def transcribe(path):
        paths.append(Path(path))
        barrier.wait(timeout=2)
        return Path(path).read_text(encoding='utf-8')
    monkeypatch.setattr(main_module, '_transcribe_audio_file', transcribe)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main_module.app), base_url='http://test') as client:
            responses = await asyncio.gather(*(client.post('/speech_to_text',
                files={'file': ('same.wav', text.encode(), 'audio/wav')}) for text in ('first', 'second')))
            assert [r.status_code for r in responses] == [200, 200]
            assert [r.json()['text'] for r in responses] == ['first', 'second']
    asyncio.run(check())
    assert len(set(paths)) == 2
    assert all(not path.parent.exists() for path in paths)


def test_slow_audio_decoder_does_not_block_health(main_module, monkeypatch):
    started, release = threading.Event(), threading.Event()
    def decode(path):
        started.set()
        release.wait(0.8)
        return Audio()
    monkeypatch.setitem(sys.modules, 'pydub', SimpleNamespace(AudioSegment=SimpleNamespace(from_file=decode)))
    monkeypatch.setattr(main_module, '_transcribe_audio_file', lambda _: 'ok')
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main_module.app), base_url='http://test') as client:
            task = asyncio.create_task(client.post('/speech_to_text', files={'file': ('file.mp3', b'fake', 'audio/mpeg')}))
            try:
                while not started.is_set():
                    await asyncio.sleep(0.005)
                health = await asyncio.wait_for(client.get('/health'), 0.3)
                assert health.status_code == 200 and not task.done()
            finally:
                release.set()
                assert (await task).status_code == 200
    asyncio.run(check())


@pytest.mark.parametrize('filename', ['same.wav', '../../private.json', r'..\..\private.json', 'C:/outside.wav', 'тест записи.mp3'])
def test_filename_is_metadata_and_never_a_destination(filename):
    paths = []
    def transcribe(path):
        paths.append(Path(path))
        assert Path(path).read_bytes() == b'original'
        assert Path(path).name.startswith('input.')
        return 'recognized'
    status, body = audio_uploads.transcribe_upload(b'original', filename, transcribe)
    assert status == 200 and body['filename'] == filename
    assert not paths[0].parent.exists()


def test_cancelled_request_leaves_cleanup_to_the_running_worker(main_module, monkeypatch):
    started, release, completed = threading.Event(), threading.Event(), threading.Event()
    paths = []
    original = audio_uploads.transcribe_upload
    def transcribe(path):
        paths.append(Path(path))
        started.set()
        release.wait(2)
        assert Path(path).read_bytes() == b'original'
        return 'ok'
    def worker(*args):
        try:
            return original(*args)
        finally:
            completed.set()
    monkeypatch.setattr(main_module, '_transcribe_audio_file', transcribe)
    monkeypatch.setattr(audio_uploads, 'transcribe_upload', worker)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main_module.app), base_url='http://test') as client:
            task = asyncio.create_task(client.post('/speech_to_text', files={'file': ('same.wav', b'original', 'audio/wav')}))
            try:
                assert await asyncio.to_thread(started.wait, 1)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert paths[0].exists()
            finally:
                release.set()
            assert await asyncio.to_thread(completed.wait, 1)
    asyncio.run(check())
    assert not paths[0].parent.exists()


@pytest.mark.parametrize('duration,loudness,message', [(399, -12, 'audio_too_short'), (800, -76, 'audio_too_quiet')])
def test_bad_audio_returns_400_without_inference(monkeypatch, duration, loudness, message):
    class BadAudio(Audio):
        dBFS = loudness
        def __len__(self):
            return duration
    monkeypatch.setitem(sys.modules, 'pydub', SimpleNamespace(AudioSegment=SimpleNamespace(from_file=lambda _: BadAudio())))
    status, body = audio_uploads.transcribe_upload(b'fake', 'file.wav', lambda _: pytest.fail('should not transcribe'))
    assert status == 400 and message in body['message']


@pytest.mark.parametrize('level', [-48, -57])
def test_quiet_audio_reaches_shared_recognizer_without_clipping_or_double_gain(monkeypatch, level):
    audio = Audio()
    audio.dBFS = level
    monkeypatch.setitem(sys.modules, 'pydub', SimpleNamespace(AudioSegment=SimpleNamespace(from_file=lambda _: audio)))
    def transcribe(path):
        assert Path(path).suffix == '.mp3'
        assert Path(path).read_bytes() == b'mp3'
        return 'ok'
    assert audio_uploads.transcribe_upload(b'mp3', 'file.mp3', transcribe)[0] == 200
    assert not hasattr(audio, 'gain')


def test_failed_recognition_cleans_up_its_directory():
    paths = []
    def fail(path):
        paths.append(Path(path))
        raise RuntimeError('recognizer failed')
    status, body = audio_uploads.transcribe_upload(b'fake', 'file.wav', fail)
    assert status == 500 and not body['success']
    assert not paths[0].parent.exists()


def test_empty_file_is_rejected_before_decoding():
    status, body = audio_uploads.transcribe_upload(b'', 'file.wav', lambda _: pytest.fail('should not transcribe'))
    assert status == 400 and not body['success']
