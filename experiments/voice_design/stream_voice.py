"""Process-local Qwen prefix decoding and continuous DSP for optional speech streams."""
import numpy as np
from scipy.signal import butter, sosfilt


class ColourStream:
    """Retain filter, oscillator and delay state across PCM blocks."""
    def __init__(self, rate, profile=None):
        self.rate, self.profile, self.offset = rate, profile, 0
        if profile is not None:
            self.band = butter(2,[65,min(7200,rate*.45)],btype='bandpass',fs=rate,output='sos')
            self.low = butter(2,1400,btype='lowpass',fs=rate,output='sos')
            self.band_state = np.zeros((len(self.band),2))
            self.low_state = np.zeros((len(self.low),2))
            self.delay = np.zeros(max(1,round(rate*profile['delay_ms']/1000)))

    def process(self, values):
        values = np.asarray(values,dtype=np.float64)
        if values.ndim != 1 or not values.size or not np.isfinite(values).all():
            raise ValueError('Invalid stream audio')
        if self.profile is None:
            return values.astype(np.float32)
        clean,self.band_state=sosfilt(self.band,values,zi=self.band_state)
        body,self.low_state=sosfilt(self.low,clean,zi=self.low_state)
        consonants=clean-body
        carrier=np.cos(2*np.pi*self.profile['carrier_hz']*(self.offset+np.arange(len(values)))/self.rate)
        metallic=body*carrier
        delayed=np.concatenate([self.delay,metallic])
        self.delay=delayed[-len(self.delay):].copy()
        self.offset+=len(values)
        return (clean+self.profile['body_mix']*(metallic-body)+self.profile['presence']*consonants
            +self.profile['resonance']*delayed[:len(values)]).astype(np.float32)


class StreamVolume:
    """Choose gain once, preserving pauses and preventing per-block pumping."""
    def __init__(self):
        self.gain=None

    def process(self, values):
        values=np.asarray(values,dtype=np.float32)
        if values.ndim!=1 or not values.size or not np.isfinite(values).all():
            raise ValueError('Invalid stream audio')
        peak=float(np.abs(values).max())
        if self.gain is None and peak>1e-5:
            rms=float(np.sqrt(np.mean(values.astype(np.float64)**2)))
            self.gain=min(4.,.065/max(rms,1e-6),.95/peak)
        return np.clip(values*(self.gain if self.gain is not None else 1.),-.95,.95).astype(np.float32)


class PrefixStream:
    """Observe one talker batch without replacing SDK code or its sampling rules."""
    def __init__(self, model, prompt, emit, profile=None, interval=12):
        self.model,self.emit,self.interval=model,emit,interval
        self.codes=[]
        self.emitted=0
        self.reference=prompt[0].ref_code.to(model.device)
        self.frame_samples=model.model.speech_tokenizer.model.decode_upsample_rate
        self.rate=24000
        self.eos=model.model.config.talker_config.codec_eos_token_id
        self.colour=ColourStream(self.rate,profile)
        self.volume=StreamVolume()
        self.profile_volume=StreamVolume() if profile is not None else None

    def publish(self, values, last):
        values=self.colour.process(self.volume.process(values))
        if self.profile_volume is not None:
            values=self.profile_volume.process(values)
        self.emit(values,self.rate,last)

    def observe(self, module, inputs, result):
        import torch
        code=result.hidden_states[-1]
        if code is None:
            return
        if code.ndim!=2 or code.shape[0]!=1:
            raise ValueError('Streaming requires one utterance')
        if int(code[0,0])==self.eos:
            return
        self.codes.append(code.detach())
        if len(self.codes)%self.interval:
            return
        prefix=torch.cat([self.reference,torch.stack(self.codes,dim=1)[0]],dim=0)
        waves,rate=self.model.model.speech_tokenizer.decode([{'audio_codes':prefix}])
        if rate!=self.rate:
            raise ValueError('Unexpected stream rate')
        values=waves[0][self.reference.shape[0]*self.frame_samples:]
        # Hold two frames at the decoder's changing right edge.
        end=len(values)-2*self.frame_samples
        if end>self.emitted:
            self.publish(values[self.emitted:end],False)
            self.emitted=end

    def finish(self, full_audio, rate):
        if rate!=self.rate or self.emitted>=len(full_audio):
            raise ValueError('Invalid final stream audio')
        self.publish(full_audio[self.emitted:],True)

    def __enter__(self):
        self.hook=self.model.model.talker.register_forward_hook(self.observe)
        return self

    def __exit__(self,*args):
        self.hook.remove()
