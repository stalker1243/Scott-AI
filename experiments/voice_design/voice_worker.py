"""Offline Scott Voice worker: JSON lines on stdout, libraries on stderr."""
from pathlib import Path
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
        from qwen_tts import Qwen3TTSModel
        from qwen_tts.core.models.modeling_qwen3_tts import Qwen3TTSRMSNorm
        torch.set_num_threads(self.config.cpu_threads)
        if self.config.device=='cuda' and not torch.cuda.is_available():
            raise RuntimeError('CUDA unavailable')
        if self.config.rms_norm:
            def fused_norm(owner, values):
                return torch.nn.functional.rms_norm(values,owner.weight.shape,owner.weight,owner.variance_epsilon)
            Qwen3TTSRMSNorm.forward = fused_norm
        self.model = Qwen3TTSModel.from_pretrained(str(self.config.model_dir),device_map=self.config.device,
             dtype=torch.bfloat16 if self.config.device=='cuda' else torch.float32,
             attn_implementation='sdpa',local_files_only=True)
        reference = json.loads(self.config.reference_json.read_text(encoding='utf-8'))
        self.prompt = self.model.create_voice_clone_prompt(
             ref_audio=str(self.config.reference_json.parent/'scott-reference.wav'),
             ref_text=reference['reference_text'],x_vector_only_mode=False)

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
