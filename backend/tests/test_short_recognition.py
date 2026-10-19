"""Clip boundary context stays narrow and never changes speech samples."""
from types import SimpleNamespace

import numpy as np
import pytest
import speech_to_text as stt

pytestmark = pytest.mark.unit

@pytest.fixture(autouse=True)
def settings(monkeypatch):
    monkeypatch.setattr(stt, 'SHORT_PADDING_MS', 300)
    monkeypatch.setattr(stt, '_подсказка', lambda: 'Скотт. Компьютер.')

@pytest.mark.parametrize('model', ['turbo', 'large-v3-turbo'])
@pytest.mark.parametrize('size', [1, 8000, 32000])
def test_short_context_preserves_samples_without_mutating_input(model, size):
    values = np.full(size, .25, np.float32)
    padded = stt.pad_short_audio(values, model)
    assert padded.dtype == np.float32 and padded.flags.c_contiguous
    assert padded.size == size+9600
    np.testing.assert_array_equal(padded[4800:-4800], values)
    assert not padded[:4800].any() and not padded[-4800:].any()
    np.testing.assert_array_equal(values, np.full(size, .25, np.float32))

@pytest.mark.parametrize('model,size', [('small', 8000), ('large-v3', 8000), ('turbo', 32001), ('turbo', 0)])
def test_other_models_and_long_clips_keep_input(model, size):
    values = np.full(size, .25, np.float32)
    assert stt.pad_short_audio(values, model) is values

def test_padding_can_be_disabled(monkeypatch):
    monkeypatch.setattr(stt, 'SHORT_PADDING_MS', 0)
    values = np.ones(8000, np.float32)
    assert stt.pad_short_audio(values, 'turbo') is values
    assert stt.pad_short_audio('recording.wav', 'turbo') == 'recording.wav'

@pytest.mark.parametrize('engine', ['openai-whisper', 'faster-whisper'])
def test_normal_first_pass_preserves_input_in_both_engines(monkeypatch, engine):
    values = np.sin(np.arange(16000)/20).astype(np.float32)*.2
    calls, vad = [], []
    recognizer = stt.Recognizer('turbo', 'cpu')
    recognizer.engine = engine
    monkeypatch.setattr(recognizer, '_есть_речь', lambda audio: vad.append(audio.copy()) or True)
    def decode(audio, **options):
        calls.append((audio, options))
        return ([SimpleNamespace(text='Скотт, стоп')], None) if engine == 'faster-whisper' else {'text': 'Скотт, стоп'}
    recognizer._model = SimpleNamespace(transcribe=decode)
    assert recognizer.transcribe(values) == 'Скотт, стоп'
    assert len(calls) == len(vad) == 1
    np.testing.assert_array_equal(vad[0], values)
    supplied, options = calls[0]
    np.testing.assert_array_equal(supplied, values)
    assert options['initial_prompt'] == 'Скотт. Компьютер.'
    assert options['temperature'] == stt.TEMPERATURES
    assert options['condition_on_previous_text'] is False

def test_short_silence_is_rejected_before_model_load(monkeypatch):
    recognizer = stt.Recognizer('turbo', 'cpu')
    monkeypatch.setattr(recognizer, 'load', lambda: pytest.fail('Silence must not load model'))
    assert recognizer.transcribe(np.zeros(8000, np.float32)) == ''


def result(text, score=-.6, silence=.01):
    return {'text': text, 'segments': [{'avg_logprob': score, 'no_speech_prob': silence}]}


def run_retry(monkeypatch, second, *, first=None, model='turbo', size=8000, fail=False):
    values = np.sin(np.arange(size)/20).astype(np.float32)*.2
    calls = []
    recognizer = stt.Recognizer(model, 'cpu')
    recognizer.engine = 'openai-whisper'
    monkeypatch.setattr(recognizer, '_есть_речь', lambda audio: True)
    def decode(audio, **options):
        calls.append((audio, options))
        if len(calls) == 1: return first or result('Голос, голос, голос.', -.7)
        if fail: raise RuntimeError('decoder failed')
        return second
    recognizer._model = SimpleNamespace(transcribe=decode)
    return recognizer.transcribe(values), calls, values


def test_one_context_retry_recovers_loop_without_rewriting_words(monkeypatch):
    text, calls, values = run_retry(monkeypatch, result('Скотт, стоп', -.6))
    assert text == 'Скотт, стоп' and len(calls) == 2
    np.testing.assert_array_equal(calls[0][0], values)
    np.testing.assert_array_equal(calls[1][0][4800:-4800], values)
    assert calls[0][1] == calls[1][1]


@pytest.mark.parametrize('first', ['Скотт, тише', 'Скотт продолжит секундомер', 'Скотт сколько будет 15% от старта'])
def test_other_uncertain_or_wrong_words_are_never_retried(monkeypatch, first):
    text, calls, _ = run_retry(monkeypatch, result('Скотт стоп'), first=result(first, -1.5))
    assert text == first and len(calls) == 1


@pytest.mark.parametrize('second', [
    result('Голос, голос, голос', -.2), result('Скотт стоп', -.9),
    result('Скотт стоп', -.2, .8), result('Спасибо за просмотр', -.1),
    {'text': 'Скотт стоп'}, result('', -.2), result('Скотт стоп', float('nan')),
])
def test_invalid_or_weaker_retry_preserves_first_transcript(monkeypatch, second):
    text, calls, _ = run_retry(monkeypatch, second)
    assert text == 'Голос, голос, голос.' and len(calls) == 2


@pytest.mark.parametrize('model,size', [('small', 8000), ('turbo', 32001)])
def test_other_models_and_long_repetitions_are_not_retried(monkeypatch, model, size):
    text, calls, _ = run_retry(monkeypatch, result('Скотт стоп'), model=model, size=size)
    assert text == 'Голос, голос, голос.' and len(calls) == 1


def test_missing_metrics_or_disabled_context_does_not_retry(monkeypatch):
    text, calls, _ = run_retry(monkeypatch, result('Скотт стоп'), first={'text': 'Голос, голос, голос'})
    assert text == 'Голос, голос, голос' and len(calls) == 1
    monkeypatch.setattr(stt, 'SHORT_PADDING_MS', 0)
    _, calls, _ = run_retry(monkeypatch, result('Скотт стоп'))
    assert len(calls) == 1


def test_retry_failure_follows_existing_error_recovery(monkeypatch):
    with pytest.raises(RuntimeError, match='decoder failed'):
        run_retry(monkeypatch, result('Скотт стоп'), fail=True)


def test_faster_repetition_keeps_existing_decoder_policy(monkeypatch):
    calls = []
    recognizer = stt.Recognizer('turbo', 'cpu')
    recognizer.engine = 'faster-whisper'
    monkeypatch.setattr(recognizer, '_есть_речь', lambda audio: True)
    def decode(audio, **options):
        calls.append(options)
        return [SimpleNamespace(text='Голос, голос, голос')], None
    recognizer._model = SimpleNamespace(transcribe=decode)
    assert recognizer.transcribe(np.ones(8000, np.float32)*.2) == 'Голос, голос, голос'
    assert len(calls) == 1
