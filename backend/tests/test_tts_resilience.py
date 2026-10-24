"""Synthesis failure/concurrency must not publish incomplete audio files."""

import asyncio
import threading
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

import scott_voice as tts
import listener as listener_module
import numpy as np

pytestmark = pytest.mark.unit


def write_wav(path):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(b"\x01\x00" * 240)
    return str(path)


@pytest.fixture
def voice(tmp_path, monkeypatch):
    import audio_settings
    monkeypatch.setattr(audio_settings, "get_character", lambda: "natural")
    instance = tts.ScottVoice.__new__(tts.ScottVoice)
    instance.audio_dir = tmp_path
    instance.engine = None
    instance._придать_характер = lambda *args: None
    return instance


def test_concurrent_synthesis_shares_one_complete_cache_file(voice, monkeypatch):
    started = threading.Event()
    release = threading.Event()
    calls = []

    destination = voice.audio_dir / 'scott_fixture.wav'
    def synthesize(text, profile, generation):
        if destination.exists():
            return str(destination)
        calls.append(text)
        def generate(path):
            Path(path).write_bytes(b'partial')
            started.set()
            assert release.wait(2)
            return write_wav(path)
        return voice._cache_synthesis(destination, generate)
    monkeypatch.setattr(tts.scott_voice_engine, 'get_engine', lambda: SimpleNamespace(
        generation=0, synthesize=synthesize))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(voice.speak_to_file, "Привет", "scott-voice")
        try:
            assert started.wait(1)
            assert not list(voice.audio_dir.glob("scott_*.wav")), "Partial file exposed as cache"
            second = pool.submit(voice.speak_to_file, "Привет", "scott-voice")
        finally:
            release.set()
        first_path, second_path = first.result(), second.result()
    assert first_path == second_path
    assert len(calls) == 1
    with wave.open(first_path) as output:
        assert output.getnframes() == 240
    assert not list(voice.audio_dir.glob(".scott-*"))


def test_failed_synthesis_discards_partial_file(voice):
    def synthesize(path):
        Path(path).write_bytes(b"partial")
        return None

    assert voice._cache_synthesis(voice.audio_dir / "failed.wav", synthesize) is None
    assert list(voice.audio_dir.iterdir()) == []


def test_conversion_exception_cleans_partial_audio(voice):
    def fail(path):
        Path(path).write_bytes(b'partial')
        raise TimeoutError('conversion timed out')
    with pytest.raises(TimeoutError):
        voice._cache_synthesis(voice.audio_dir / 'failed.wav', fail)
    assert list(voice.audio_dir.iterdir()) == []


def test_scott_voice_returns_actual_wav_without_conversion(voice, monkeypatch):
    calls = []
    path = voice.audio_dir / 'scott.wav'
    def synthesize(text, profile, generation):
        calls.append(path)
        return write_wav(path)
    monkeypatch.setattr(tts.scott_voice_engine, 'get_engine', lambda: SimpleNamespace(
        generation=0, synthesize=synthesize))
    path = voice.speak_to_file("Тест", "scott-voice")
    assert path.endswith(".wav")
    assert Path(calls[0]).suffix == ".wav"
    with wave.open(path) as output:
        assert output.getnframes() > 0
    assert not list(voice.audio_dir.glob(".scott-*"))


def test_pause_during_recognition_discards_pending_command():
    started = threading.Event()
    release = threading.Event()
    commands = []
    interrupted = []

    def transcribe(audio):
        started.set()
        release.wait(2)
        return "Скотт тест"

    listener = listener_module.VoiceListener(transcribe=transcribe, handle_command=commands.append,
                                             on_interrupt=interrupted.append)
    listener._running = True
    listener._phrases.put((np.zeros(100, dtype=np.float32), False, 0))
    worker = threading.Thread(target=listener._process_loop)
    listener._threads = [worker]
    worker.start()
    try:
        assert started.wait(1)
        assert listener.stop()["success"]
    finally:
        release.set()
        worker.join(timeout=2)
    assert not worker.is_alive()
    assert not commands
    assert interrupted == [""]


def test_restart_rejects_a_previous_worker_still_exiting():
    listener = listener_module.VoiceListener(transcribe=lambda _: "", handle_command=lambda _: None)
    listener._threads = [SimpleNamespace(is_alive=lambda: True)]
    result = listener.start()
    assert not result["success"]
    assert listener._stream is None


def test_recognizer_load_is_idempotent(monkeypatch):
    import speech_to_text
    loads = []
    recognizer = speech_to_text.Recognizer("fake", "cpu")

    def load():
        loads.append(True)
        recognizer._model = object()
        recognizer.engine = "fake"

    monkeypatch.setattr(recognizer, "_load", load)
    assert recognizer.load() == recognizer.load() == "fake"
    assert loads == [True]


def test_concurrent_recognition_does_not_share_decoder_state(monkeypatch):
    import speech_to_text
    started = threading.Event()
    release = threading.Event()
    second_started = threading.Event()

    def transcribe(audio, **kwargs):
        name = 'first' if np.isclose(audio[0],.02) else 'second'
        if name == "first":
            started.set()
            release.wait(2)
        else:
            second_started.set()
        return {"text": name}

    recognizer = speech_to_text.Recognizer("fake", "cpu")
    recognizer.engine = "openai-whisper"
    recognizer._model = SimpleNamespace(transcribe=transcribe)
    monkeypatch.setattr(recognizer,'_есть_речь',lambda audio:True)
    # This checks decoder serialization; discovering real installed apps is a
    # separate boundary and can consume the entire handshake deadline.
    monkeypatch.setattr(speech_to_text,'_подсказка',lambda:'synthetic decoder fixture')
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(recognizer.transcribe, np.full(16000,.02,dtype=np.float32))
        try:
            assert started.wait(1)
            second = pool.submit(recognizer.transcribe, np.full(16000,.03,dtype=np.float32))
            assert not second_started.wait(0.05)
        finally:
            release.set()
        assert first.result() == "first"
        assert second.result() == "second"
