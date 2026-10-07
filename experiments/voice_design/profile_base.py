"""Profile local Base synthesis without loading or mutating Scott's app modules."""
from pathlib import Path
import argparse
import functools
import hashlib
import json
import sys
import time

from trial_utils import ROOT, HERE, cases, prepare_text, save_json, write_audio


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/voice-speed')
    parser.add_argument('--full-trace', action='store_true', help='Collect a full synthesis trace; may use many GB of RAM')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    import torch
    from qwen_tts import Qwen3TTSModel
    torch.set_num_threads(4)
    reference = json.loads((ROOT/'reports/voice-design/reference/reference.json').read_text(encoding='utf-8'))
    reference_audio = ROOT/'reports/voice-design/reference/scott-reference.wav'
    if hashlib.sha256(reference_audio.read_bytes()).hexdigest() != reference['sha256']:
        raise ValueError('Selected reference hash mismatch')
    model = Qwen3TTSModel.from_pretrained(str(HERE/'models/base'), device_map='cuda',
                  dtype=torch.bfloat16, attn_implementation='sdpa', local_files_only=True)
    prompt = model.create_voice_clone_prompt(ref_audio=str(reference_audio),
                     ref_text=reference['reference_text'], x_vector_only_mode=False)
    case = next(row for row in cases() if row['id']=='status')

    def generate():
        torch.manual_seed(20261006)
        with torch.inference_mode():
            return model.generate_voice_clone(text=prepare_text(case['text']), language='Russian',
                   voice_clone_prompt=prompt, non_streaming_mode=False, max_new_tokens=256,
                   temperature=.7, top_p=.95, subtalker_temperature=.7)

    generate()
    torch.cuda.synchronize()
    started = time.perf_counter()
    waves, rate = generate()
    torch.cuda.synchronize()
    normal_seconds = time.perf_counter()-started
    metrics = write_audio(waves[0], rate, args.output/'profile-status.wav')
    records = {}

    def instrument(owner, method, label):
        original = getattr(owner, method)
        records[label] = dict(calls=0, wall_seconds=0.0)
        @functools.wraps(original)
        def measured(*values, **options):
            started = time.perf_counter()
            with torch.profiler.record_function(label):
                result = original(*values, **options)
            records[label]['calls'] += 1
            records[label]['wall_seconds'] += time.perf_counter()-started
            if label == 'scott/code_predictor.generate' and records[label]['calls'] == 2 and not args.full_trace:
                profile.toggle_collection_dynamic(False, activities)
            return result
        setattr(owner, method, measured)

    instrument(model.model.talker.code_predictor, 'generate', 'scott/code_predictor.generate')
    instrument(model.model.speech_tokenizer, 'decode', 'scott/audio_decode')
    activities = [torch.profiler.ProfilerActivity.CPU]
    if torch.profiler.kineto_available():
        activities.append(torch.profiler.ProfilerActivity.CUDA)
    print(json.dumps(dict(phase='profiling', normal_seconds=round(normal_seconds,3))), flush=True)
    started = time.perf_counter()
    with torch.profiler.profile(activities=activities, record_shapes=False, profile_memory=False, with_stack=False) as profile:
        generate()
        torch.cuda.synchronize()
    elapsed = time.perf_counter()-started
    averages = list(profile.key_averages())
    def event(row):
        return dict(name=row.key, calls=row.count, self_cpu_ms=round(row.self_cpu_time_total/1000,3),
                    cpu_total_ms=round(row.cpu_time_total/1000,3),
                    self_device_ms=round(row.self_device_time_total/1000,3),
                    device_total_ms=round(row.device_time_total/1000,3))
    result = dict(case=case, **metrics, normal_seconds=round(normal_seconds,3), profiled_seconds=round(elapsed,3),
                  sections=records,
                  top_cpu=[event(row) for row in sorted(averages,key=lambda row:row.self_cpu_time_total,reverse=True)[:20]],
                  top_device=[event(row) for row in sorted(averages,key=lambda row:row.self_device_time_total,reverse=True)[:20]],
                  scope='full synthesis' if args.full_trace else 'prefill and first two code-predictor calls',
                  note='Instrumented wall times include profiler overhead; compare speed only on the unprofiled run.')
    save_json(args.output/'profile.json', result)
    print(json.dumps(dict(profiled_seconds=result['profiled_seconds'], sections=records)),flush=True)


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream,'reconfigure'):
            stream.reconfigure(encoding='utf-8',errors='replace')
    main()
