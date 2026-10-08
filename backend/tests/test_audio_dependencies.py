"""Exercise real audio dependencies without models, devices or cloud requests."""
import wave

import numpy as np
import pytest

import speech_to_text

pytestmark = pytest.mark.unit


@pytest.fixture
def stereo_recording(tmp_path):
    rate = 24000
    mono = (np.sin(np.arange(rate) * 2 * np.pi * 440 / rate) * 8000).astype('<i2')
    stereo = np.column_stack((mono, mono)).astype('<i2')
    path = tmp_path / 'synthetic stereo.wav'
    with wave.open(str(path), 'wb') as recording:
        recording.setnchannels(2)
        recording.setsampwidth(2)
        recording.setframerate(rate)
        recording.writeframes(stereo.tobytes())
    return path


def test_real_decoder_returns_mono_16khz_without_ffmpeg(monkeypatch, stereo_recording):
    monkeypatch.setenv('PATH', '')
    audio = speech_to_text.prepare_audio(stereo_recording)
    assert audio.shape == (16000,)
    assert audio.dtype == np.float32
    assert np.isfinite(audio).all() and np.max(np.abs(audio)) > .1


def test_real_fallback_can_import_and_read_wav(stereo_recording):
    import speech_recognition as sr

    with sr.AudioFile(str(stereo_recording)) as source:
        audio = sr.Recognizer().record(source)
    assert audio.sample_rate == 24000
    assert audio.sample_width == 2
    assert len(audio.frame_data) == 24000 * 2
