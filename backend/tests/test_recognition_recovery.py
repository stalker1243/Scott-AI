"""Both Whisper engines apply the same controls and recover from GPU failure."""

from types import SimpleNamespace
import sys
import pytest
import speech_to_text

pytestmark = pytest.mark.unit
REAL_PROMPT = speech_to_text._подсказка


@pytest.fixture(autouse=True)
def prompt(monkeypatch):
    monkeypatch.setattr(speech_to_text, '_подсказка', lambda: 'Скотт. Голос, компьютер, Айдар.')


def recognizer(text):
    model = speech_to_text.Recognizer('fake', 'cpu')
    model.engine = 'openai-whisper'
    model._model = SimpleNamespace(transcribe=lambda *a, **k: {'text': text})
    return model


@pytest.mark.parametrize('text', ['Редактор субтитров О.Голубкина', 'Спасибо за просмотр!', 'Продолжение следует...'])
def test_plain_whisper_does_not_dispatch_hallucinations(text):
    assert recognizer(text).transcribe('fake.wav') == ''


def test_plain_whisper_has_prompt_and_bounded_decoding():
    calls = []
    model = recognizer('Скотт, открой браузер')
    model._model = SimpleNamespace(transcribe=lambda *a, **k: calls.append(k) or {'text': 'ok'})
    assert model.transcribe('fake.wav') == 'ok'
    assert calls[0]['temperature'] == speech_to_text.TEMPERATURES
    assert 'Айдар' in calls[0]['initial_prompt']


def test_broken_prompt_builder_falls_back_to_words(monkeypatch):
    import speech_hints
    monkeypatch.setattr(speech_hints, 'prompt', lambda: (_ for _ in ()).throw(RuntimeError('catalog failed')))
    prompt = REAL_PROMPT().casefold()
    assert 'скотт' in prompt
    assert not any(verb in prompt for verb in ('открой', 'закрой', 'выключи', 'удали'))


def test_gpu_failure_retries_once_on_cpu_and_keeps_working_model(monkeypatch):
    monkeypatch.setattr(speech_to_text, 'ENGINE_CHOICE', 'openai')
    loads = []
    def load(name, device):
        loads.append(device)
        def transcribe(*a, **k):
            if device == 'cuda':
                raise RuntimeError('CUDA out of memory')
            return {'text': 'Скотт, сколько времени'}
        return SimpleNamespace(transcribe=transcribe)
    monkeypatch.setitem(sys.modules, 'whisper', SimpleNamespace(load_model=load))
    model = speech_to_text.Recognizer('fake', 'cuda')
    assert model.transcribe('fake.wav') == 'Скотт, сколько времени'
    assert model.device == 'cpu'
    assert model.transcribe('fake.wav') == 'Скотт, сколько времени'
    assert loads == ['cuda', 'cpu']


def test_cpu_failure_is_not_retried_forever():
    model = recognizer('')
    model._model = SimpleNamespace(transcribe=lambda *a, **k: (_ for _ in ()).throw(RuntimeError('out of memory')))
    with pytest.raises(RuntimeError):
        model.transcribe('fake.wav')


def test_non_device_error_preserves_gpu_model():
    model = recognizer('')
    model.device = 'cuda'
    original = SimpleNamespace(transcribe=lambda *a, **k: (_ for _ in ()).throw(RuntimeError('bad audio')))
    model._model = original
    with pytest.raises(RuntimeError, match='bad audio'):
        model.transcribe('fake.wav')
    assert model._model is original and model.device == 'cuda'


def test_fast_whisper_recovers_when_lazy_segments_fail(monkeypatch):
    monkeypatch.setattr(speech_to_text, 'ENGINE_CHOICE', 'faster')
    loads = []
    def load(name, device, compute_type):
        loads.append(device)
        def transcribe(*a, **k):
            def segments():
                if device == 'cuda':
                    raise RuntimeError('cuDNN failed to initialize')
                yield SimpleNamespace(text='Скотт, сколько времени')
            return segments(), None
        return SimpleNamespace(transcribe=transcribe)
    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(WhisperModel=load))
    model = speech_to_text.Recognizer('fake', 'cuda')
    assert model.transcribe('fake.wav') == 'Скотт, сколько времени'
    assert model.transcribe('fake.wav') == 'Скотт, сколько времени'
    assert loads == ['cuda', 'cpu']


@pytest.mark.parametrize('engine', ['openai-whisper', 'faster-whisper'])
def test_background_without_speech_skips_inference(monkeypatch, engine):
    model = recognizer('')
    model.engine = engine
    monkeypatch.setattr(model, '_есть_речь', lambda audio: False)
    def unexpected(*args, **kwargs):
        pytest.fail('Background must not enter the model decoder')
    model._model = SimpleNamespace(transcribe=unexpected)
    assert model.transcribe('fake.wav') == ''
