"""Reference loading without a real model, GPU, network or personal audio."""
import contextlib
import io
import json
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace
import wave

import numpy as np
import pytest

pytestmark = pytest.mark.unit


def write_pcm(path, samples, channels=1):
    with wave.open(str(path),'wb') as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes((samples*32768).astype('<i2').tobytes())


@pytest.fixture
def worker(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[2]/'voice/runtime/voice_worker.py'
    # The executable reserves stdout for its protocol. Restore both stream
    # and import path after loading its class into this test process.
    original_path = list(sys.path)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            namespace = runpy.run_path(str(path), run_name='test_voice_worker')
    finally:
        sys.path[:] = original_path
    calls = []
    prompt = object()
    models = []
    fail_prompt = [False]
    class Model:
        def create_voice_clone_prompt(self, **kwargs):
            calls.append(('prompt',kwargs))
            if fail_prompt[0]:
                raise RuntimeError('Reference encoding failed')
            return prompt
    def pretrained(*args, **kwargs):
        calls.append(('model',args,kwargs))
        model = Model()
        models.append(model)
        return model
    norm = type('Norm', (), {'forward': lambda self,values:values})
    monkeypatch.setitem(sys.modules,'qwen_tts',SimpleNamespace(Qwen3TTSModel=SimpleNamespace(from_pretrained=pretrained)))
    monkeypatch.setitem(sys.modules,'qwen_tts.core.models.modeling_qwen3_tts',SimpleNamespace(Qwen3TTSRMSNorm=norm))
    torch = SimpleNamespace(set_num_threads=lambda count:calls.append(('threads',count)),
        cuda=SimpleNamespace(is_available=lambda:False),float32='float32',bfloat16='bf16')
    monkeypatch.setitem(sys.modules,'torch',torch)
    def read(path, *, dtype):
        calls.append(('reference_read',path,dtype))
        assert dtype=='float32'
        try:
            with wave.open(str(path),'rb') as source:
                samples = np.frombuffer(source.readframes(source.getnframes()),dtype='<i2').astype(np.float32)/32768
                if source.getnchannels()>1:
                    samples = samples.reshape(-1,source.getnchannels())
                return samples,source.getframerate()
        except (OSError,EOFError,wave.Error) as error:
            raise RuntimeError('Cannot read reference') from error
    monkeypatch.setitem(sys.modules,'soundfile',SimpleNamespace(read=read))
    reference = tmp_path/'reference.json'
    reference.write_text(json.dumps({'reference_text':'Test reference.'}),encoding='utf-8')
    samples = np.arange(-120,120,dtype=np.float32)/32768
    write_pcm(reference.with_name('scott-reference.wav'),samples)
    synth = namespace['Synthesizer'].__new__(namespace['Synthesizer'])
    synth.config = SimpleNamespace(reference_json=reference,model_dir=tmp_path/'model',
        device='cpu',cpu_threads=4,rms_norm=False)
    synth.model = synth.prompt = None
    return SimpleNamespace(synth=synth,calls=calls,prompt=prompt,models=models,
        fail_prompt=fail_prompt,samples=samples,norm=norm,torch=torch)


def test_reference_uses_original_pcm_without_general_path_loader(worker):
    forward = worker.norm.forward
    worker.synth.load()
    args = next(call[1] for call in worker.calls if call[0]=='prompt')
    audio, rate = args['ref_audio']
    assert np.array_equal(audio,worker.samples) and audio.dtype==np.float32
    assert rate==24000 and args['ref_text']=='Test reference.'
    assert args['x_vector_only_mode'] is False
    assert next(call for call in worker.calls if call[0]=='reference_read')[2]=='float32'
    model_call = next(call for call in worker.calls if call[0]=='model')
    assert model_call[2]==dict(device_map='cpu',dtype='float32',attn_implementation='sdpa',local_files_only=True)
    assert worker.norm.forward is forward  # No silent acceleration/voice change.
    assert worker.synth.model is worker.models[0] and worker.synth.prompt is worker.prompt
    count = len(worker.calls)
    worker.synth.load()
    assert len(worker.calls)==count


def test_failed_prompt_does_not_publish_partial_model_and_retry_loads(worker):
    worker.fail_prompt[0] = True
    with pytest.raises(RuntimeError,match='Reference encoding failed'):
        worker.synth.load()
    assert worker.synth.model is None and worker.synth.prompt is None
    worker.fail_prompt[0] = False
    worker.synth.load()
    assert len(worker.models)==2
    assert worker.synth.model is worker.models[1] and worker.synth.prompt is worker.prompt


@pytest.mark.parametrize('kind',['missing','corrupt','stereo','empty'])
def test_bad_reference_fails_before_model_allocation(worker,kind):
    reference = worker.synth.config.reference_json.with_name('scott-reference.wav')
    if kind=='missing':
        reference.unlink()
    elif kind=='corrupt':
        reference.write_bytes(b'not audio')
    else:
        samples = np.zeros((10,2) if kind=='stereo' else (0,),dtype=np.float32)
        write_pcm(reference,samples,channels=2 if kind=='stereo' else 1)
    with pytest.raises((RuntimeError,ValueError)):
        worker.synth.load()
    assert worker.synth.model is None and worker.synth.prompt is None
    assert not worker.models


def test_missing_cuda_fails_before_model_allocation(worker):
    worker.synth.config.device = 'cuda'
    with pytest.raises(RuntimeError,match='CUDA unavailable'):
        worker.synth.load()
    assert not worker.models and worker.synth.model is None
