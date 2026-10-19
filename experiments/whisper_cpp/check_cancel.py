"""Real worker: cross-thread cancellation, no late text, clean reload and shutdown."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import shutil
import threading
import time

from benchmark import ROOT, Native, read_prompt_tokens, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('worker', 'model', 'corpus', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--device', choices=('cpu', 'vulkan'), default='cpu')
    parser.add_argument('--beam-size', type=int, choices=range(1, 9), default=5)
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
    if not args.model.is_relative_to(ROOT/'reports'):
        parser.error('Use experimental weights inside reports')
    args.output.mkdir(parents=True)
    args.threads, args.fallback, args.owner_watch = 8, 0, True
    fixtures = args.output/'fixtures'
    fixtures.mkdir()
    shutil.copy2(args.corpus/'prompt.txt', fixtures/'prompt.txt')
    pcm = (args.corpus/'000.f32').read_bytes()
    (fixtures/'000.f32').write_bytes(pcm)
    length = 16000*30*4
    (fixtures/'long.f32').write_bytes((pcm*((length+len(pcm)-1)//len(pcm)))[:length])
    checks, trials = [], []
    worker = None
    def check(name, value):
        checks.append(dict(name=name, passed=bool(value)))
        write_json(args.output/'partial.json', dict(checks=checks, trials=trials))
        if not value: raise AssertionError(name)
    try:
        worker = Native(args, fixtures, args.output)
        owner_monitor = worker.ready.get('owner_monitor')
        check('owner_bound', worker.ready['owner_monitor']['pid'] == os.getpid())
        check('beam_reported', worker.ready['decoder_options']['beam_size'] == args.beam_size)
        reference = worker.transcribe(dict(id=1, pcm='000.f32'))
        check('initial_decode', bool(reference.get('text')) and not reference.get('error'))
        worker.close()
        check('idle_eof_exit_zero', worker.process.returncode == 0)
        for index, operation in enumerate(('cancel', 'cancel', 'cancel', 'close', 'race')):
            folder = args.output/f'trial-{index}'
            folder.mkdir()
            worker = Native(args, fixtures, folder)
            responses = []
            def decode():
                try:
                    responses.append(worker.transcribe(dict(id=2, pcm='long.f32')))
                except Exception as error:
                    responses.append(dict(error=type(error).__name__))
            thread = threading.Thread(target=decode)
            thread.start()
            deadline = time.monotonic()+2
            while not worker.request_lock.locked() and time.monotonic() < deadline:
                time.sleep(.001)
            time.sleep(.15)
            check(f'active_{index}', thread.is_alive() and worker.process.poll() is None)
            check(f'reject_parallel_{index}', worker.transcribe(dict(id=3, pcm='000.f32')).get('error') == 'busy')
            started = time.perf_counter()
            if operation == 'cancel': worker.cancel()
            elif operation == 'close': worker.close()
            else:
                gate = threading.Barrier(2)
                errors = []
                def stop(action):
                    try:
                        gate.wait(timeout=2)
                        action()
                    except Exception as error:
                        errors.append(type(error).__name__)
                closers = [threading.Thread(target=stop, args=(action,)) for action in (worker.cancel, worker.close)]
                for closer in closers: closer.start()
                for closer in closers: closer.join(timeout=2)
                check('simultaneous_stop', not errors and all(not closer.is_alive() for closer in closers))
            thread.join(timeout=2)
            elapsed = time.perf_counter()-started
            check(f'cancel_bounded_{index}', not thread.is_alive() and elapsed < 2)
            check(f'cancel_result_{index}', len(responses) == 1 and responses[0].get('error') == 'cancelled')
            check(f'no_late_text_{index}', not responses[0].get('text'))
            worker.process.wait(timeout=2)
            exit_seconds = time.perf_counter()-started
            check(f'process_exit_bounded_{index}', exit_seconds < 2)
            check(f'worker_stopped_{index}', worker.process.poll() is not None)
            check(f'no_reuse_{index}', worker.transcribe(dict(id=4, pcm='000.f32')).get('error') == 'cancelled')
            check(f'cancel_idempotent_{index}', worker.cancel() is False)
            worker.close(); worker.close()
            check(f'threads_stopped_{index}', not worker.monitor_thread.is_alive() and not worker.reader_thread.is_alive())
            trials.append(dict(operation=operation, caller_seconds=elapsed,
                process_exit_seconds=exit_seconds, result=responses[0]))
        folder = args.output/'late-result'
        folder.mkdir()
        worker = Native(args, fixtures, folder)
        received, release = threading.Event(), threading.Event()
        original_receive = worker.receive
        decoded, responses = [], []
        def delayed_receive(timeout):
            result = original_receive(timeout)
            decoded.append(result)
            received.set()
            if not release.wait(timeout=10): raise RuntimeError('late_result_gate_timeout')
            return result
        worker.receive = delayed_receive
        def decode_late():
            responses.append(worker.transcribe(dict(id=6, pcm='000.f32')))
        thread = threading.Thread(target=decode_late)
        thread.start()
        try:
            check('real_result_waiting', received.wait(timeout=120) and bool(decoded[0].get('text')))
            check('cancel_queued_result', worker.cancel())
        finally:
            release.set()
            thread.join(timeout=2)
        check('discard_queued_result', not thread.is_alive() and responses[0].get('error') == 'cancelled')
        check('no_queued_text', not responses[0].get('text'))
        worker.process.wait(timeout=2)
        check('queued_worker_stopped', worker.process.poll() is not None)
        worker.close()
        check('queued_threads_stopped', not worker.monitor_thread.is_alive() and not worker.reader_thread.is_alive())
        folder = args.output/'reloaded'
        folder.mkdir()
        worker = Native(args, fixtures, folder)
        restored = worker.transcribe(dict(id=5, pcm='000.f32'))
        check('reload_same_text', restored.get('text') == reference['text'])
        worker.close()
        check('reload_eof_exit_zero', worker.process.returncode == 0)
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        for index, value in enumerate((True, -1, 2147483648, 1 if os.getpid() != 1 else 2)):
            invalid = subprocess.run([str(args.worker), str(args.model), str(args.corpus), 'cpu', '8',
                str(args.corpus/'prompt.txt'), '0', json.dumps(dict(owner_pid=value))], input='',
                text=True, encoding='utf-8', stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=10, creationflags=flags)
            check(f'reject_owner_{index}', invalid.returncode != 0 and '"event":"ready"' not in invalid.stdout)
        write_json(args.output/'result.json', dict(checks=checks, trials=trials,
            owner_monitor=owner_monitor,
            microphone_used=False, playback_used=False, commands_executed=False))
        print(json.dumps(dict(passed=len(checks), trials=trials)))
    finally:
        if worker: worker.close(force=True)


if __name__ == '__main__':
    main()
