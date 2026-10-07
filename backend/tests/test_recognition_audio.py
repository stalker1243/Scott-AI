"""Input quality safeguards, shared by microphone and file recognition."""
from types import SimpleNamespace
import sys

import numpy as np
import pytest
import speech_to_text as stt

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('audio', [np.zeros(0, np.float32), np.zeros(16000, np.float32), np.zeros(40000, np.float32)])
def test_silence_never_loads_or_calls_whisper(monkeypatch, audio):
    model = stt.Recognizer('fake', 'cpu')
    monkeypatch.setattr(model, 'load', lambda: pytest.fail('Silent input must not load Whisper'))
    assert model.transcribe(audio) == ''


@pytest.mark.parametrize('engine', ['openai-whisper', 'faster-whisper'])
def test_uploaded_recording_uses_same_vad_and_gain_as_microphone(monkeypatch, tmp_path, engine):
    path = tmp_path / 'message.wav'
    path.write_bytes(b'fixture handled by decoder')
    wave = np.sin(np.arange(40000) / 13).astype(np.float32) * .002
    decode_calls, inference = [], []
    def decode(name, sampling_rate):
        decode_calls.append((name, sampling_rate))
        return wave
    monkeypatch.setitem(sys.modules, 'faster_whisper.audio', SimpleNamespace(decode_audio=decode))
    recognizer = stt.Recognizer('fake', 'cpu')
    recognizer.engine = engine
    vad_calls = []
    monkeypatch.setattr(recognizer, '_есть_речь', lambda audio: vad_calls.append(audio.copy()) or True)
    def transcribe(audio, **options):
        inference.append((audio, options))
        return ([SimpleNamespace(text='Скотт, открой браузер')], None) if engine == 'faster-whisper' else {'text': 'Скотт, открой браузер'}
    recognizer._model = SimpleNamespace(transcribe=transcribe)
    assert recognizer.transcribe(path) == 'Скотт, открой браузер'
    assert decode_calls == [(str(path), 16000)]
    np.testing.assert_array_equal(vad_calls[0], wave)  # Do not amplify noise for VAD.
    np.testing.assert_allclose(inference[0][0], wave * 8)
    assert inference[0][1]['beam_size'] > 1
    assert not inference[0][1]['condition_on_previous_text']


def test_quiet_gain_does_not_clip_transients_or_change_normal_speech():
    normal = np.sin(np.arange(16000) / 17).astype(np.float32) * .2
    np.testing.assert_array_equal(stt.normalize_quiet_audio(normal), normal)
    quiet_with_click = np.ones(16000, np.float32) * .0001
    quiet_with_click[8000] = .8
    boosted = stt.normalize_quiet_audio(quiet_with_click)
    assert np.max(np.abs(boosted)) <= .901
    assert boosted.shape == quiet_with_click.shape and np.isfinite(boosted).all()


@pytest.mark.parametrize('audio', [np.array([np.nan]), np.array([np.inf]), np.zeros((5, 2))])
def test_invalid_samples_are_not_sent_to_decoder(audio):
    recognizer = stt.Recognizer('fake', 'cpu')
    recognizer._model = SimpleNamespace(transcribe=lambda *a, **kw: pytest.fail('Invalid audio'))
    with pytest.raises(ValueError):
        recognizer.transcribe(audio)


def test_no_speech_upload_does_not_enter_decoder(monkeypatch, tmp_path):
    path = tmp_path / 'background.wav'
    path.touch()
    monkeypatch.setitem(sys.modules, 'faster_whisper.audio', SimpleNamespace(decode_audio=lambda *a, **k: np.ones(48000, np.float32) * .001))
    recognizer = stt.Recognizer('fake', 'cpu')
    recognizer._model = SimpleNamespace(transcribe=lambda *a, **kw: pytest.fail('Background must not become a command'))
    monkeypatch.setattr(recognizer, '_есть_речь', lambda audio: False)
    assert recognizer.transcribe(path) == ''


def test_local_turbo_cache_keeps_official_name_and_checksum_validation(monkeypatch, tmp_path):
    monkeypatch.setattr(stt, '__file__', str(tmp_path / 'speech_to_text.py'))
    cache = tmp_path / 'data/models/whisper'
    cache.mkdir(parents=True)
    (cache / 'large-v3-turbo.pt').touch()
    calls = []
    def load(name, device, **options):
        calls.append((name, device, options))
        if device == 'cuda':
            raise RuntimeError('CUDA out of memory')
        return SimpleNamespace()
    monkeypatch.setitem(sys.modules, 'whisper', SimpleNamespace(load_model=load))
    monkeypatch.setattr(stt, 'ENGINE_CHOICE', 'openai')
    model = stt.Recognizer('turbo', 'cuda')
    assert model.load() == 'openai-whisper'
    assert model.device == 'cpu'
    assert calls == [('turbo', 'cuda', {'download_root': str(cache)}),
                     ('turbo', 'cpu', {'download_root': str(cache)})]
