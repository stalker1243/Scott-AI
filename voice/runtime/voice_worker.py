"""Offline Scott Voice worker: JSON lines on stdout, libraries on stderr."""
from pathlib import Path
from contextlib import contextmanager
import argparse
import json
import os
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0,str(ROOT))
protocol_output = sys.stdout
sys.stdout = sys.stderr

from backend.scott_voice_process import (PROTOCOL, MAX_TEXT, PROFILES, VoiceProcessConfig,
                                        recipe_id, audio_key, cached_audio, publish_audio, watch_owner,
                                        stream_path, checksum)


def emit(value):
    protocol_output.write(json.dumps(value,ensure_ascii=False)+'\n')
    protocol_output.flush()


def _top_level_package(path):
    import inspect
    parts = path.parts
    if not parts:
        raise ValueError('Empty metadata path')
    return parts[0] if len(parts)>1 else inspect.getmodulename(path) or str(path)


def _record_package_names(distribution, record):
    import csv
    from importlib.metadata import PackagePath
    names = set()
    for row in csv.reader(record.splitlines()):
        if not 1<=len(row)<=3:
            raise ValueError('Nonstandard RECORD')
        # Distribution.files validates every size, even for an import name
        # already found. Keep malformed metadata on the standard error path.
        if len(row)==3 and row[2]:
            int(row[2])
        path = PackagePath(row[0])
        name = _top_level_package(path)
        # Inference needs one existing member of each top-level package.
        # A missing first member must still try later recorded members.
        if name not in names and distribution.locate_file(path).exists():
            names.add(name)
    return names


def _fast_packages_distributions(original):
    import csv
    import importlib.metadata as metadata
    from collections import defaultdict
    result = defaultdict(list)
    for distribution in metadata.distributions():
        declared = (distribution.read_text('top_level.txt') or '').split()
        if declared:
            names = declared
        else:
            record = distribution.read_text('RECORD') if type(distribution) is metadata.PathDistribution else None
            if record:
                try:
                    names = _record_package_names(distribution,record)
                except (ValueError,TypeError,csv.Error):
                    return original()
            else:
                # Custom providers and egg metadata retain their files property.
                # Provider failures propagate without a second attempt.
                names = {_top_level_package(path) for path in (distribution.files or ())}
            names = (name for name in names if '.' not in name)
        for name in names:
            result[name].append(distribution.metadata['Name'])
    return dict(result)


@contextmanager
def _metadata_catalog():
    # Match the qualified SDK's CPython metadata inference. Other interpreters
    # use their own implementation unchanged.
    if sys.implementation.name!='cpython' or sys.version_info[:2]!=(3,13):
        yield
        return
    import importlib.metadata as metadata
    original = metadata.packages_distributions
    def catalog():
        return _fast_packages_distributions(original)
    metadata.packages_distributions = catalog
    try:
        yield
    finally:
        if metadata.packages_distributions is catalog:
            metadata.packages_distributions = original


def _cuda_norm_graphs(model, norm_type):
    """Replay the original small RMS operations; cache belongs to this worker."""
    import threading
    import types
    import torch
    # This path is qualified with the pinned CUDA SDK. Other versions retain
    # their own implementation, including any future upstream fused kernels.
    if (str(torch.__version__)!='2.14.1+cu126'
            or norm_type.__module__!='qwen_tts.core.models.modeling_qwen3_tts'
            or norm_type.forward.__name__!='forward'):
        return None
    modules = [module for module in model.modules() if type(module) is norm_type]
    if len(modules)!=134:
        return None
    owner_thread = threading.get_ident()
    cache = {}
    shapes = {(1,1,1024),(1,2,1024),(1,1,16,128),
              (1,2,16,128),(1,1,8,128),(1,2,8,128)}
    missing = object()

    def patch(owner):
        original = owner.forward
        def forward(module, values):
            weight = module.weight
            if (threading.get_ident()!=owner_thread or torch.is_grad_enabled()
                    or not values.is_cuda or values.dtype is not torch.bfloat16
                    or tuple(values.shape) not in shapes or not values.is_contiguous()
                    or not weight.is_cuda or weight.device!=values.device
                    or weight.dtype is not torch.bfloat16 or not weight.is_contiguous()
                    or tuple(weight.shape)!=(values.shape[-1],)
                    or module.variance_epsilon!=1e-6
                    or torch.cuda.is_current_stream_capturing()):
                return original(values)
            stream = torch.cuda.current_stream(values.device)
            key = (values.device.index,stream.cuda_stream,tuple(values.shape))
            entry = cache.get(key,missing)
            if entry is None:
                return original(values)
            if entry is missing:
                if len(cache)>=8:
                    return original(values)
                static_input = torch.empty_like(values)
                static_weight = torch.empty_like(weight)
                static_input.copy_(values)
                static_weight.copy_(weight)
                proxy = norm_type(weight.numel(),eps=module.variance_epsilon)
                proxy.weight = torch.nn.Parameter(static_weight,requires_grad=False)
                proxy.eval()
                side = torch.cuda.Stream(device=values.device)
                side.wait_stream(stream)
                with torch.cuda.stream(side):
                    for _ in range(3):
                        proxy(static_input)
                side.synchronize()
                graph = torch.cuda.CUDAGraph()
                # Use PyTorch's capture context and its allocator/stream guards.
                # Capture failures propagate to the existing owned-worker error
                # handler; do not retry work on a possibly failed CUDA context.
                with torch.cuda.graph(graph,stream=side):
                    output = proxy(static_input)
                stream.wait_stream(side)
                graph.replay()
                expected = original(values)
                # Each shape verifies its first real result. A mismatch disables
                # that entry; no tolerance, resampling or change to the voice.
                if not torch.equal(output,expected):
                    cache[key] = None
                    return expected
                entry = (static_input,static_weight,graph,output,proxy,side)
                cache[key] = entry
            else:
                static_input,static_weight,graph,output,proxy,side = entry
                # Different trained layers share the graph, never their weights.
                static_input.copy_(values)
                static_weight.copy_(weight)
                graph.replay()
            # Callers can retain a hidden state across later norm calls. Never
            # expose the reusable graph buffer as their result.
            return entry[3].clone()
        owner.forward = types.MethodType(forward,owner)

    for module in modules:
        patch(module)
    return cache


class Synthesizer:
    def __init__(self, config):
        self.config = config
        self.recipe = recipe_id(config)
        self.profiles = {row['id']:row for row in json.loads(config.profiles_json.read_text(encoding='utf-8'))}
        self.model = None
        self.prompt = None

    def load(self):
        if self.model is not None:
            return
        import torch
        import soundfile as sf
        with _metadata_catalog():
            from qwen_tts import Qwen3TTSModel
            from qwen_tts.core.models.modeling_qwen3_tts import Qwen3TTSRMSNorm
        torch.set_num_threads(self.config.cpu_threads)
        if self.config.device=='cuda' and not torch.cuda.is_available():
            raise RuntimeError('CUDA unavailable')
        if self.config.rms_norm:
            def fused_norm(owner, values):
                return torch.nn.functional.rms_norm(values,owner.weight.shape,owner.weight,owner.variance_epsilon)
            Qwen3TTSRMSNorm.forward = fused_norm
        reference = json.loads(self.config.reference_json.read_text(encoding='utf-8'))
        # The bundled reference is mono PCM. Passing its original float32
        # samples avoids librosa's general-purpose path loader on every cold
        # worker; Qwen accepts (waveform, sample_rate) directly.
        audio, rate = sf.read(self.config.reference_json.parent/'scott-reference.wav',dtype='float32')
        if audio.ndim!=1 or not len(audio):
            raise ValueError('Invalid reference audio')
        model = Qwen3TTSModel.from_pretrained(str(self.config.model_dir),device_map=self.config.device,
             dtype=torch.bfloat16 if self.config.device=='cuda' else torch.float32,
             attn_implementation='sdpa',local_files_only=True)
        prompt = model.create_voice_clone_prompt(
             ref_audio=(audio,rate),
             ref_text=reference['reference_text'],x_vector_only_mode=False)
        # A failed prompt must not leave a model that looks ready to a retry.
        if self.config.device=='cuda' and not self.config.rms_norm:
            _cuda_norm_graphs(model.model,Qwen3TTSRMSNorm)
        self.model, self.prompt = model, prompt

    def synthesize(self, packet):
        request,text,profile,key = (packet[name] for name in ('id','text','profile','key'))
        if not isinstance(request,str) or not re.fullmatch('[0-9a-f]{32}',request):
            raise ValueError('Invalid request ID')
        if not isinstance(text,str) or not text.strip() or len(text)>MAX_TEXT or profile not in PROFILES:
            raise ValueError('Invalid request')
        streaming=packet.get('action')=='stream'
        if packet.get('action') not in ('synthesize','stream') or key != audio_key(self.recipe,text,profile):
            raise ValueError('Invalid cache identity')
        if not streaming and cached_audio(self.config.cache_dir,key):
            return dict(event='audio',id=request,key=key,cached=True,model_loaded=self.model is not None)
        import soundfile as sf
        from trial_utils import write_audio
        temporary = self.config.cache_dir/f'.pending-{request}.wav'
        sequence=0
        def stream_chunk(values,rate,last):
            nonlocal sequence
            path=stream_path(self.config.cache_dir,request,sequence)
            pending=path.with_suffix('.tmp')
            try:
                sf.write(pending,values,rate,format='WAV',subtype='PCM_16')
                os.replace(pending,path)
                emit(dict(event='chunk',id=request,key=key,sequence=sequence,last=last,sha256=checksum(path)))
                sequence+=1
            finally:
                pending.unlink(missing_ok=True)
        try:
            raw_key = audio_key(self.recipe,text,'natural')
            natural = cached_audio(self.config.cache_dir,raw_key)
            if not natural:
                self.load()
                import torch
                torch.manual_seed(20261006)
                with torch.inference_mode():
                    if streaming:
                        from stream_voice import PrefixStream
                        with PrefixStream(self.model,self.prompt,stream_chunk,
                                self.profiles.get(profile)) as stream:
                            waves,rate = self.model.generate_voice_clone(text=text,language='Russian',
                                voice_clone_prompt=self.prompt,non_streaming_mode=False,max_new_tokens=768,
                                temperature=.7,top_p=.95,subtalker_temperature=.7)
                        stream.finish(waves[0],rate)
                    else:
                        waves,rate = self.model.generate_voice_clone(text=text,language='Russian',
                            voice_clone_prompt=self.prompt,non_streaming_mode=False,max_new_tokens=768,
                            temperature=.7,top_p=.95,subtalker_temperature=.7)
                write_audio(waves[0],rate,temporary)
                publish_audio(self.config.cache_dir,raw_key,request,temporary)
                natural = cached_audio(self.config.cache_dir,raw_key)
                if not natural:
                    raise ValueError('Invalid synthesized audio')
            if profile!='natural':
                from create_scott_voice import colour_voice
                signal,rate = sf.read(natural['path'],dtype='float32')
                write_audio(colour_voice(signal,rate,self.profiles[profile]),rate,temporary)
                publish_audio(self.config.cache_dir,key,request,temporary)
            if streaming and sequence==0:
                ready=cached_audio(self.config.cache_dir,key)
                values,rate=sf.read(ready['path'],dtype='float32')
                for start in range(0,len(values),24000):
                    stream_chunk(values[start:start+24000],rate,start+24000>=len(values))
            return dict(event='audio',id=request,key=key,cached=False,model_loaded=self.model is not None)
        finally:
            temporary.unlink(missing_ok=True)
            temporary.with_suffix('.json').unlink(missing_ok=True)

    def prepare(self, packet):
        request = packet.get('id')
        if not isinstance(request,str) or not re.fullmatch('[0-9a-f]{32}',request) \
                or packet.get('recipe')!=self.recipe or set(packet)!={'id','action','recipe'}:
            raise ValueError('Invalid preparation request')
        self.load()
        if self.config.device=='cuda':
            import torch
            torch.cuda.synchronize()
        return dict(event='prepared',id=request,recipe=self.recipe)


def main():
    watch_owner()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configuration',required=True)
    args = parser.parse_args()
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_IMPLICIT_TOKEN='1',
                      HF_HOME=str(HERE/'models/cache'))
    try:
        config = VoiceProcessConfig.from_wire(json.loads(args.configuration))
        config.wire()
        config.cache_dir.mkdir(parents=True,exist_ok=True)
        synthesizer = Synthesizer(config)
    except Exception:
        emit(dict(event='error',code='configuration_failed'))
        return 1
    emit(dict(event='ready',protocol=PROTOCOL,recipe=synthesizer.recipe,features=['stream_v1','prepare_v1']))
    while True:
        line = sys.stdin.readline(65537)
        if not line:
            return 0
        if len(line)>65536 or not line.endswith('\n'):
            emit(dict(event='error',code='invalid_protocol'))
            return 1
        try:
            packet = json.loads(line)
            emit(synthesizer.prepare(packet) if packet.get('action')=='prepare' else synthesizer.synthesize(packet))
        except Exception:
            # Text and exception payloads are deliberately not printed to logs.
            emit(dict(event='error',code='synthesis_failed'))
            return 1


if __name__=='__main__':
    for stream in (protocol_output,sys.stdin,sys.stderr):
        if hasattr(stream,'reconfigure'):
            stream.reconfigure(encoding='utf-8',errors='replace')
    raise SystemExit(main())
