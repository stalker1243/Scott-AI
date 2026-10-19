"""Exercise the real worker's input isolation, timeout recovery and shutdown."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from benchmark import ROOT, Native, read_prompt_tokens, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--decoder-trace', action='store_true')
    parser.add_argument('--prompt-tokens', type=Path)
    parser.add_argument('--finish-at-eot', action='store_true')
    parser.add_argument('--rank-eot', action='store_true')
    parser.add_argument('--deduplicate-first-step', action='store_true')
    parser.add_argument('--deterministic-topk', action='store_true')
    parser.add_argument('--finished-pool', action='store_true')
    args = parser.parse_args()
    args.prompt_token_ids = read_prompt_tokens(args.prompt_tokens) if args.prompt_tokens else None
    for name in ('worker', 'model', 'corpus', 'output'):
        setattr(args, name, getattr(args, name).resolve())
    if not args.output.is_relative_to(ROOT/'reports') or args.output.exists():
        parser.error('Choose a new report directory')
    args.output.mkdir(parents=True)
    args.device, args.threads, args.fallback = 'cpu', 8, 0
    fixtures = args.output/'fixtures'
    fixtures.mkdir()
    shutil.copy2(args.corpus/'prompt.txt', fixtures/'prompt.txt')
    shutil.copy2(args.corpus/'000.f32', fixtures/'valid.f32')
    (args.output/'outside.f32').write_bytes((fixtures/'valid.f32').read_bytes())
    (fixtures/'bad-size.f32').write_bytes(b'x')
    import struct
    (fixtures/'nan.f32').write_bytes(struct.pack('<f', float('nan')))
    (fixtures/'range.f32').write_bytes(struct.pack('<f', 1.1))
    worker = None
    checks = []
    def check(name, value):
        checks.append(dict(name=name, passed=bool(value)))
        write_json(args.output/'partial.json', checks)
        if not value: raise AssertionError(name)
    for name, options in [('unknown_option', '{"unknown":true}'),
            ('option_type', '{"flash_attn":"true"}'), ('option_object', '[]'),
            ('option_size', ' '*4097), ('beam_zero', '{"beam_size":0}'),
            ('beam_large', '{"beam_size":9}'), ('beam_bool', '{"beam_size":true}'),
            ('beam_fraction', '{"beam_size":5.5}'), ('trace_type', '{"trace_tokens":"true"}'),
            ('renorm_type', '{"renormalize_timestamps":1}'),
            ('prompt_object', '{"prompt_token_ids":{}}'), ('prompt_empty', '{"prompt_token_ids":[]}'),
            ('prompt_large', json.dumps(dict(prompt_token_ids=[1]*221))),
            ('prompt_negative', '{"prompt_token_ids":[-1]}'), ('prompt_control', '{"prompt_token_ids":[50257]}'),
            ('prompt_bool', '{"prompt_token_ids":[true]}'), ('prompt_float', '{"prompt_token_ids":[1.5]}'),
            ('prompt_string', '{"prompt_token_ids":["1"]}'),
            ('prompt_overflow', '{"prompt_token_ids":[18446744073709551615]}'),
            ('prompt_space_conflict', '{"prompt_token_ids":[1],"prompt_space":true}'),
            ('finish_type', '{"finish_at_eot":1}'), ('rank_type', '{"rank_eot":"true"}'),
            ('dedup_type', '{"deduplicate_first_step":1}'), ('topk_type', '{"deterministic_topk":"true"}'),
            ('pool_type', '{"finished_pool":1}'),
            ('pool_conflict', '{"finished_pool":true,"deterministic_topk":true}')]:
        with (args.output/f'{name}.log').open('w', encoding='utf-8') as log:
            invalid = subprocess.run([str(args.worker), str(args.model), str(fixtures), 'cpu',
                '8', str(fixtures/'prompt.txt'), '0', options], input='',
                text=True, encoding='utf-8', stdout=subprocess.PIPE, stderr=log, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        check('reject_'+name, invalid.returncode != 0 and '"event":"ready"' not in invalid.stdout)
    try:
        worker = Native(args, fixtures, args.output)
        check('ready_protocol', worker.ready['protocol'] == 1)
        requests = [dict(id=1, pcm='../outside.f32'), dict(id=2, pcm=str(args.output/'outside.f32')),
            dict(id=3, pcm='missing.f32'), dict(id=4, pcm='bad-size.f32'), dict(id=5, pcm='nan.f32'),
            dict(id=6, pcm='range.f32'), dict(id=7, pcm='valid.f32', timeout_ms=0),
            dict(id=8, pcm='valid.f32', timeout_ms=120001), dict(id='x', pcm='valid.f32'),
            dict(id=10, pcm='valid.f32', op='unknown'), dict(id=11)]
        for index, request in enumerate(requests):
            worker.process.stdin.write(json.dumps(request)+'\n'); worker.process.stdin.flush()
            result = worker.receive(15)
            check(f'reject_invalid_{index}', bool(result.get('error')))
        worker.process.stdin.write('{bad json}\n'); worker.process.stdin.flush()
        check('reject_malformed_json', bool(worker.receive(15).get('error')))
        worker.process.stdin.write('x'*65537+'\n'); worker.process.stdin.flush()
        check('reject_large_line', bool(worker.receive(15).get('error')))
        start = time.perf_counter()
        result = worker.transcribe(dict(id=20, pcm='valid.f32'), timeout_ms=1)
        timeout_seconds = time.perf_counter()-start
        check('timeout_returned', result.get('error') == 'timeout')
        check('timeout_bounded', timeout_seconds < 5)
        after = worker.transcribe(dict(id=21, pcm='valid.f32'))
        check('decode_after_abort', bool(after.get('text')) and not after.get('error'))
        # The model remains reusable after invalid input and the real abort callback.
        again = worker.transcribe(dict(id=22, pcm='valid.f32'))
        check('repeat_after_abort', after['text'] == again['text'])
        pid = worker.process.pid
        worker.close()
        check('clean_eof_exit', worker.process.returncode == 0)
        check('process_stopped', not worker.owner.is_running())
        worker = Native(args, fixtures, args.output)
        start = time.perf_counter()
        active = worker.transcribe(dict(id=23, pcm='valid.f32'), timeout_ms=200)
        active_timeout_seconds = time.perf_counter()-start
        check('active_timeout', active.get('error') == 'timeout')
        check('active_timeout_bounded', active_timeout_seconds < 2)
        check('active_worker_stopped', active.get('worker_stopped') and worker.process.poll() is not None)
        worker.close()
        worker = Native(args, fixtures, args.output)
        restored = worker.transcribe(dict(id=24, pcm='valid.f32'))
        check('fresh_worker_recovers', restored.get('text') == after['text'])
        worker.close()
        write_json(args.output/'result.json', dict(checks=checks, timeout_seconds=timeout_seconds,
            active_timeout_seconds=active_timeout_seconds, worker_pid=pid,
            microphone_used=False, playback_used=False, commands_executed=False))
        print(json.dumps(dict(passed=len(checks), timeout_seconds=timeout_seconds, active_timeout_seconds=active_timeout_seconds)))
    finally:
        if worker: worker.close()


if __name__ == '__main__': main()
