"""Measure process-local Base optimizations; never change the installed SDK or app."""
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
import argparse
import functools
import hashlib
import json
import statistics
import time

from trial_utils import ROOT, HERE, cases, prepare_text, save_json, write_audio
from benchmark_base import Backend


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/voice-speed')
    parser.add_argument('--backend-url', default='http://127.0.0.1:8000')
    parser.add_argument('--candidates', nargs='+', choices=['original','no_hidden','repeat_kv','combined','efficient_kv','efficient_rms','rms'],
                        default=['original','no_hidden','repeat_kv','combined'])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    import torch
    from qwen_tts import Qwen3TTSModel
    from transformers.integrations import sdpa_attention
    from qwen_tts.core.models.modeling_qwen3_tts import Qwen3TTSRMSNorm
    from torch.nn.attention import SDPBackend, sdpa_kernel
    torch.set_num_threads(4)
    backend = Backend(args.backend_url)
    backend.get('/health')
    reference_path = ROOT/'reports/voice-design/reference/scott-reference.wav'
    reference = json.loads(reference_path.with_name('reference.json').read_text(encoding='utf-8'))
    if hashlib.sha256(reference_path.read_bytes()).hexdigest() != reference['sha256']:
        raise ValueError('Selected reference hash mismatch')
    model = Qwen3TTSModel.from_pretrained(str(HERE/'models/base'), device_map='cuda',
                 dtype=torch.bfloat16, attn_implementation='sdpa', local_files_only=True)
    prompt = model.create_voice_clone_prompt(ref_audio=str(reference_path),
                    ref_text=reference['reference_text'], x_vector_only_mode=False)
    predictor = model.model.talker.code_predictor
    original_generate = predictor.generate
    @functools.wraps(original_generate)
    def without_unused_hidden(*values, **options):
        options['output_hidden_states'] = False
        return original_generate(*values, **options)
    available = dict(flash_compiled=torch.backends.cuda.is_flash_attention_available(),
                     flash_enabled=torch.backends.cuda.flash_sdp_enabled(),
                     efficient_enabled=torch.backends.cuda.mem_efficient_sdp_enabled(),
                     cudnn_enabled=torch.backends.cuda.cudnn_sdp_enabled())
    result = dict(torch=torch.__version__, gpu=torch.cuda.get_device_name(), cpu_threads=4,
                  reference_sha256=reference['sha256'], backends=available, results=[], validation=[],
                  note='Repeat-KV avoids GQA math fallback on builds without flash kernels. All patches are process-local.')
    status = next(row for row in cases() if row['id']=='status')
    candidates = [(name, name in ('no_hidden','combined'), name in ('repeat_kv','combined','efficient_kv','efficient_rms'))
                  for name in args.candidates]

    def fused_norm(owner, hidden_states):
        return torch.nn.functional.rms_norm(hidden_states, owner.weight.shape, owner.weight, owner.variance_epsilon)

    def generate(case):
        torch.manual_seed(20261006)
        with torch.inference_mode():
            return model.generate_voice_clone(text=prepare_text(case['text']), language='Russian',
                 voice_clone_prompt=prompt, non_streaming_mode=False, max_new_tokens=768,
                 temperature=.7, top_p=.95, subtalker_temperature=.7)

    def changes(name, no_hidden, repeat_kv):
        stack = ExitStack()
        if no_hidden:
            stack.enter_context(patch.object(predictor, 'generate', without_unused_hidden))
        if repeat_kv:
            # Explicit head repetition permits efficient SDPA where native GQA needs unavailable flash.
            stack.enter_context(patch.object(sdpa_attention, 'use_gqa_in_sdpa', return_value=False))
        if name.startswith('efficient_'):
            stack.enter_context(sdpa_kernel([SDPBackend.EFFICIENT_ATTENTION, SDPBackend.MATH]))
        if name in ('efficient_rms','rms'):
            stack.enter_context(patch.object(Qwen3TTSRMSNorm, 'forward', fused_norm))
        return stack

    for name, no_hidden, repeat_kv in candidates:
        with changes(name, no_hidden, repeat_kv):
            generate(status)
            times = []
            for _ in range(2):
                torch.cuda.reset_peak_memory_stats()
                torch.cuda.synchronize()
                started = time.perf_counter()
                waves, rate = generate(status)
                torch.cuda.synchronize()
                times.append(time.perf_counter()-started)
            target = args.output/f'{name}-status.wav'
            metrics = write_audio(waves[0], rate, target)
            row = dict(candidate=name, times_seconds=[round(t,3) for t in times],
                       median_seconds=round(statistics.median(times),3),
                       real_time_factor=round(statistics.median(times)/(len(waves[0])/rate),3),
                       vram_allocated_peak_gib=round(torch.cuda.max_memory_allocated()/2**30,3),
                       sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                       recognition=backend.transcribe(target,status['text']), **metrics)
            result['results'].append(row)
            save_json(args.output/'speed.json', result)
            print(json.dumps(row, ensure_ascii=True), flush=True)
    valid = [row for row in result['results'] if row['recognition']['success'] and row['recognition']['word_error_rate']==0]
    winner = min(valid, key=lambda row:row['median_seconds'])
    name, no_hidden, repeat_kv = next(options for options in candidates if options[0]==winner['candidate'])
    result['winner'] = name
    original = next((row for row in result['results'] if row['candidate']=='original'), None)
    result['speedup'] = round(original['median_seconds']/winner['median_seconds'],3) if original else None
    if name != 'original':
        with changes(name, no_hidden, repeat_kv):
            for case in [row for row in cases() if row['id'] in ('technical','numbers')]:
                torch.cuda.synchronize()
                started = time.perf_counter()
                waves, rate = generate(case)
                torch.cuda.synchronize()
                elapsed = time.perf_counter()-started
                target = args.output/f'{name}-{case["id"]}.wav'
                metrics = write_audio(waves[0], rate, target)
                row = dict(**case, **metrics, synthesis_seconds=round(elapsed,3),
                           recognition=backend.transcribe(target,case['text']))
                result['validation'].append(row)
                save_json(args.output/'speed.json', result)
                print(json.dumps(row, ensure_ascii=True), flush=True)
    result['health'], _ = backend.get('/health')
    save_json(args.output/'speed.json', result)
    print(json.dumps(dict(winner=name, speedup=result['speedup'])), flush=True)


if __name__ == '__main__':
    main()
