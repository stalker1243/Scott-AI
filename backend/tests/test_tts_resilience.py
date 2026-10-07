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

    def synthesize(text, path, selected_voice):
        calls.append(path)
        Path(path).write_bytes(b"partial")
        started.set()
        release.wait(2)
        return write_wav(path)

    monkeypatch.setattr(tts, "HAS_SILERO", True)
    monkeypatch.setattr(tts.silero_tts, "synthesize", synthesize)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(voice.speak_to_file, "Привет", "aidar")
        try:
            assert started.wait(1)
            assert not list(voice.audio_dir.glob("scott_*.wav")), "Partial file exposed as cache"
            second = pool.submit(voice.speak_to_file, "Привет", "aidar")
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


def test_edge_timeout_is_bounded_and_cleans_partial_audio(voice, monkeypatch):
    cancelled = []

    class Communicate:
        def __init__(self, *args, **kwargs):
            pass

        async def save(self, path):
            Path(path).write_bytes(b"partial mp3")
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)

    monkeypatch.setattr(tts, "HAS_EDGE_TTS", True)
    monkeypatch.setattr(tts, "EDGE_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(tts.edge_tts, "Communicate", Communicate)
    result = voice._cache_synthesis(voice.audio_dir / "failed.mp3",
                                    lambda path: voice._save_edge_tts("Тест", path))
    assert result is None
    assert cancelled == [True]
    assert list(voice.audio_dir.iterdir()) == []


def test_failed_edge_uses_system_voice_with_wav_extension(voice, monkeypatch):
    calls = []
    monkeypatch.setattr(tts, "HAS_SILERO", False)
    monkeypatch.setattr(tts, "HAS_EDGE_TTS", True)
    voice.engine = object()
    voice._save_edge_tts = lambda *args: None

    def system_voice(text, path):
        calls.append(path)
        return write_wav(path)

    voice._speak_sync = system_voice
    path = voice.speak_to_file("Тест", "ru-RU-DmitryNeural")
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


def test_concurrent_recognition_does_not_share_decoder_state():
    import speech_to_text
    started = threading.Event()
    release = threading.Event()
    second_started = threading.Event()

    def transcribe(audio, **kwargs):
        if audio == "first":
            started.set()
            release.wait(2)
        else:
            second_started.set()
        return {"text": audio}

    recognizer = speech_to_text.Recognizer("fake", "cpu")
    recognizer.engine = "openai-whisper"
    recognizer._model = SimpleNamespace(transcribe=transcribe)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(recognizer.transcribe, "first")
        try:
            assert started.wait(1)
            second = pool.submit(recognizer.transcribe, "second")
            assert not second_started.wait(0.05)
        finally:
            release.set()
        assert first.result() == "first"
        assert second.result() == "second"
