"""Decoder preparation must work even when VAD correctly rejects synthetic noise."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

import numpy as np
import pytest
import speech_to_text as stt
import device_settings

pytestmark=pytest.mark.unit

@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(stt,'_подсказка',lambda:'Скотт. Synthetic program.')
    monkeypatch.setattr(device_settings,'rocm_build',lambda:False)
    def make(engine):
        recognizer=stt.Recognizer('turbo','cuda')
        recognizer.engine=engine
        calls=[];vad=[]
        def decode(audio,**options):
            calls.append((audio.copy(),options))
            if engine=='openai-whisper':return {'text':'Голос, голос, голос'}
            def segments():
                calls[-1][1]['iterated']=True
                yield SimpleNamespace(text='Синтетическая фраза')
            return segments(),None
        recognizer._model=SimpleNamespace(transcribe=decode)
        monkeypatch.setattr(recognizer,'_есть_речь',lambda audio:vad.append(audio.copy()) or False)
        return recognizer,calls,vad
    return make

@pytest.mark.parametrize('seconds',[.5,15])
def test_rejected_noise_still_prepares_decoder_once(fake,seconds):
    engine='openai-whisper'
    recognizer,calls,vad=fake(engine)
    assert recognizer.warmup(seconds) is None
    assert len(calls)==len(vad)==1
    raw=(np.random.default_rng(1).standard_normal(int(16000*seconds))*.01).astype(np.float32)
    np.testing.assert_array_equal(vad[0],raw)
    np.testing.assert_array_equal(calls[0][0],stt.normalize_quiet_audio(raw))
    options=calls[0][1]
    assert options['temperature']==[0.0]  # No random fallback on artificial background.
    assert options['beam_size']==stt.BEAM_SIZE and options['best_of']==5
    assert options['language']=='ru' and not options['condition_on_previous_text']
    assert options['initial_prompt']=='Скотт. Synthetic program.'
    if engine=='faster-whisper':assert options['iterated']
    else:assert options['fp16']

@pytest.mark.parametrize('engine',['openai-whisper','faster-whisper'])
def test_real_background_and_silence_are_still_filtered_after_warmup(fake,engine):
    recognizer,calls,vad=fake(engine)
    recognizer.warmup()
    expected=1 if engine=='openai-whisper' else 0
    assert len(calls)==expected
    assert recognizer.transcribe(np.zeros(24000,np.float32))==''
    assert recognizer.transcribe(np.ones(48000,np.float32)*.003)==''
    assert len(calls)==expected and len(vad)==2

@pytest.mark.parametrize('engine',['openai-whisper','faster-whisper'])
def test_warmup_never_changes_real_decode_options(fake,monkeypatch,engine):
    recognizer,calls,vad=fake(engine)
    recognizer.warmup()
    monkeypatch.setattr(recognizer,'_есть_речь',lambda audio:True)
    recognizer.transcribe(np.ones(48000,np.float32)*.2,language='de')
    options=calls[-1][1]
    assert options['temperature']==stt.TEMPERATURES
    assert options['beam_size']==stt.BEAM_SIZE and options['best_of']==5
    assert options['language']=='de' and not options['condition_on_previous_text']

def test_warmup_gpu_failure_uses_existing_single_cpu_recovery(fake,monkeypatch):
    recognizer,calls,vad=fake('openai-whisper')
    loads=[]
    def load():
        loads.append(recognizer.device)
        recognizer.engine='openai-whisper'
        recognizer._model=SimpleNamespace(transcribe=lambda *a,**kw:{'text':''})
    recognizer._model=SimpleNamespace(transcribe=lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('CUDA out of memory')))
    monkeypatch.setattr(recognizer,'_load',load)
    recognizer.warmup()
    assert loads==['cpu'] and recognizer.device=='cpu'

@pytest.mark.parametrize('device,message',[('cpu','out of memory'),('cuda','bad decoder')])
def test_warmup_does_not_hide_nonrecoverable_failure(fake,monkeypatch,device,message):
    recognizer,_,_=fake('openai-whisper')
    recognizer.device=device
    if device=='cpu':monkeypatch.setattr(recognizer,'_есть_речь',lambda audio:True)
    recognizer._model=SimpleNamespace(transcribe=lambda *a,**kw:(_ for _ in ()).throw(RuntimeError(message)))
    with pytest.raises(RuntimeError,match=message):recognizer.warmup()

def test_real_request_cannot_enter_decoder_during_warmup(fake,monkeypatch):
    recognizer,_,_=fake('openai-whisper')
    entered,release,second=Event(),Event(),Event()
    calls=[]
    monkeypatch.setattr(recognizer,'_есть_речь',lambda audio:True)
    def decode(audio,**kw):
        calls.append(kw['temperature'])
        if len(calls)==1:
            entered.set();assert release.wait(2)
        else:second.set()
        return {'text':''}
    recognizer._model=SimpleNamespace(transcribe=decode)
    with ThreadPoolExecutor(2) as pool:
        warm=pool.submit(recognizer.warmup)
        try:
            assert entered.wait(1)
            normal=pool.submit(recognizer.transcribe,np.ones(48000,np.float32)*.2)
            assert not second.wait(.05)
        finally:release.set()
        warm.result(2);assert normal.result(2)==''
    assert calls==[[0.0],stt.TEMPERATURES]

@pytest.mark.parametrize('device,engine,hip',[
    ('cpu','openai-whisper',False),('cpu','faster-whisper',False),
    ('cuda','faster-whisper',False),('cuda','openai-whisper',True)])
def test_unqualified_backends_keep_original_noise_filter(fake,monkeypatch,device,engine,hip):
    recognizer,calls,vad=fake(engine)
    recognizer.device=device
    monkeypatch.setattr(device_settings,'rocm_build',lambda:hip)
    recognizer.warmup()
    assert len(vad)==1 and calls==[]

def test_zero_length_warmup_does_not_load_model(fake,monkeypatch):
    recognizer,_,_=fake('openai-whisper')
    monkeypatch.setattr(recognizer,'load',lambda:pytest.fail('Empty warmup must not load a model'))
    recognizer.warmup(0)
