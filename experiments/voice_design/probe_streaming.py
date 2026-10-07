"""Observe offline Qwen code frames and measure prefix decoding without playback."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import time

from trial_utils import ROOT, cases, prepare_text, save_json, write_audio


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/voice-stream-probe')
    parser.add_argument('--frames', type=int, default=12)
    parser.add_argument('--case', choices=['status','technical','numbers'], default='status')
    args = parser.parse_args()
    if args.frames < 4 or args.frames > 48:
        raise ValueError('Invalid frame interval')
    if (args.output/'probe.json').exists():
        raise ValueError('Use a new report directory')
    args.output.mkdir(parents=True,exist_ok=True)
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_IMPLICIT_TOKEN='1')
    import numpy as np
    import torch
    from qwen_tts import Qwen3TTSModel
    torch.set_num_threads(4)
    home = ROOT/'voice-runtime'
    reference = home/'reports/voice-design/reference/scott-reference.wav'
    metadata = json.loads(reference.with_name('reference.json').read_text(encoding='utf-8'))
    assert hashlib.sha256(reference.read_bytes()).hexdigest()==metadata['sha256']
    started=time.perf_counter()
    model=Qwen3TTSModel.from_pretrained(str(home/'experiments/voice_design/models/base'),
        device_map='cuda',dtype=torch.bfloat16,attn_implementation='sdpa',local_files_only=True)
    prompt=model.create_voice_clone_prompt(ref_audio=str(reference),ref_text=metadata['reference_text'],x_vector_only_mode=False)
    load=time.perf_counter()-started
    case=next(c for c in cases() if c['id']==args.case)
    codes, pieces, arrivals, decode_times = [], [], [], []
    emitted=0
    frame_samples=model.model.speech_tokenizer.model.decode_upsample_rate
    stop_id=model.model.config.talker_config.codec_eos_token_id
    ref=prompt[0].ref_code.to(model.device)
    def observe(module, inputs, result):
        nonlocal emitted
        code=result.hidden_states[-1]
        if code is None or int(code[0,0])==stop_id:
            return
        codes.append(code.detach())
        if len(codes)%args.frames:
            return
        started_decode=time.perf_counter()
        prefix=torch.cat([ref,torch.stack(codes,dim=1)[0]],dim=0)
        wavs,rate=model.model.speech_tokenizer.decode([{'audio_codes':prefix}])
        wav=wavs[0][ref.shape[0]*frame_samples:]
        end=len(wav)-2*frame_samples
        if end>emitted:
            pieces.append(wav[emitted:end].copy())
            emitted=end
            arrivals.append(dict(frames=len(codes),samples=emitted,seconds=round(time.perf_counter()-begin,3)))
        decode_times.append(time.perf_counter()-started_decode)
        print(json.dumps(dict(frames=len(codes),emitted_seconds=round(emitted/rate,3),elapsed=round(time.perf_counter()-begin,3))),flush=True)
    hook=model.model.talker.register_forward_hook(observe)
    begin=time.perf_counter()
    try:
        torch.manual_seed(20261006)
        with torch.inference_mode():
            waves,rate=model.generate_voice_clone(text=prepare_text(case['text']),language='Russian',voice_clone_prompt=prompt,
                non_streaming_mode=False,max_new_tokens=768,temperature=.7,top_p=.95,subtalker_temperature=.7)
    finally:
        hook.remove()
    total=time.perf_counter()-begin
    pieces.append(waves[0][emitted:].copy())
    joined=np.concatenate(pieces)
    assert len(joined)==len(waves[0]) and np.isfinite(joined).all()
    metrics=write_audio(waves[0],rate,args.output/'complete.wav')
    streamed_metrics=write_audio(joined,rate,args.output/'streamed.wav')
    result=dict(**case,load_seconds=round(load,3),total_seconds=round(total,3),
        reference_sha256=metadata['sha256'],frame_samples=frame_samples,frames=len(codes),
        complete=metrics,streamed=streamed_metrics,arrivals=arrivals,
        decode_seconds=round(sum(decode_times),3),max_difference=float(np.abs(joined-waves[0]).max()),
        rms_difference=float(np.sqrt(np.mean((joined.astype(np.float64)-waves[0])**2))),
        sha256=hashlib.sha256((args.output/'complete.wav').read_bytes()).hexdigest(),
        vram_peak_gib=round(torch.cuda.max_memory_allocated()/2**30,3))
    save_json(args.output/'probe.json',result)
    print(json.dumps({k:result[k] for k in ('total_seconds','decode_seconds','max_difference','rms_difference','sha256','vram_peak_gib')}),flush=True)


if __name__=='__main__':
    main()
