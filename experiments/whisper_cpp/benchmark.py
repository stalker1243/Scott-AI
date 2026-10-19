"""Saved synthetic audio only: isolated source, no microphone, playback or actions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import statistics
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools'))
from compare_recognition import read_wav, sha


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def read_prompt_tokens(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT/'reports') or not path.is_file() or path.stat().st_size > 4096:
        raise ValueError('Prompt token file must be a small experimental reports file')
    ids = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(ids, list) or not 1 <= len(ids) <= 220 or any(
            type(id) is not int or not 0 <= id < 50257 for id in ids):
        raise ValueError('Prompt requires 1–220 ordinary integer token IDs')
    return ids


def isolated(source):
    sys.path.insert(0, str(source))
    sys.dont_write_bytecode = True
    os.chdir(source)
    os.environ.update(WHISPER_ENGINE='openai', WARMUP_MODELS='0', SCOTT_SEMANTIC_MEMORY='0',
        OPENAI_API_KEY='', GROQ_API_KEY='', DEEPSEEK_API_KEY='', AI_PROVIDER='', AI_MODEL='')
    from testing_guard import install
    install([ROOT/'backend/data', ROOT/'data', ROOT/'.env', ROOT/'audio_cache'])


def prepare(destination):
    import numpy as np
    destination.mkdir(parents=True)
    source = destination/'source/backend'
    source.mkdir(parents=True)
    for file in (ROOT/'backend').glob('*.py'): shutil.copy2(file, source/file.name)
    (source.parent/'.env').write_text('WARMUP_MODELS=0\nSCOTT_SEMANTIC_MEMORY=0\n', encoding='utf-8')
    isolated(source)
    import speech_to_text as stt
    import check_recognition
    probe = stt.Recognizer('turbo', 'cpu')  # VAD/input checks only; no model load.
    prompt = stt._подсказка()
    (destination/'prompt.txt').write_text(prompt, encoding='utf-8')
    originals = []
    samples = []
    def add(corpus, text, condition, voice, audio):
        index = len(samples)
        pcm = f'{index:03}.f32'
        gate = (not audio.size or np.max(np.abs(audio)) <= 1e-7 or not probe._есть_речь(audio))
        raw = np.asarray(audio, dtype='<f4')
        cooked = np.asarray(stt.normalize_quiet_audio(raw), dtype='<f4')
        raw.tofile(destination/f'{index:03}-raw.f32')
        cooked.tofile(destination/pcm)
        samples.append(dict(id=index, corpus=corpus, reference=text, condition=condition, voice=voice,
            pcm=pcm, raw=f'{index:03}-raw.f32', sha256=sha(destination/pcm),
            gated=bool(gate), clip_seconds=len(audio)/16000))
    trial = ROOT/'reports/voice-path/audio-trial-2'
    for row in json.loads((trial/'result.json').read_text(encoding='utf-8'))['rows']:
        path = trial/row['audio']
        originals.append(dict(path=str(path.relative_to(ROOT)), sha256=sha(path)))
        add('new_tools', row['reference'], row['condition'], 'original', read_wav(path))
    for index, text in enumerate(check_recognition.PHRASES):
        voice = ('aidar', 'eugene')[index % 2]
        path = ROOT/f'reports/recognition-turbo/{index:02}-{voice}.wav'
        originals.append(dict(path=str(path.relative_to(ROOT)), sha256=sha(path)))
        for condition, audio in check_recognition.variants(read_wav(path), index).items():
            add('previous', text, condition, voice, audio)
    from validate_recognition import CONTROLS
    for voice in ('aidar', 'eugene', 'baya', 'kseniya'):
        for index, text in enumerate(CONTROLS):
            for condition in ('clean', 'noise_15db'):
                path = ROOT/f'reports/recognition-retry/validation/control-{voice}-{index:02}-{condition}.wav'
                originals.append(dict(path=str(path.relative_to(ROOT)), sha256=sha(path)))
                add('activation_controls', text, condition, voice, read_wav(path))
    rng = np.random.default_rng(581)
    for index in range(12):
        length = (8000, 16000, 48000)[index % 3]
        add('background', '', 'noise', 'none', rng.normal(0, .003, length).astype(np.float32))
    add('background', '', 'silence', 'none', np.zeros(8000, np.float32))
    write_json(destination/'manifest.json', dict(samples=samples, originals=originals,
        prompt_sha256=sha(destination/'prompt.txt'), source_sha256={f.name:sha(f) for f in source.glob('*.py')}))
    print(json.dumps(dict(prepared=len(samples))), flush=True)


class Native:
    def __init__(self, args, corpus, output):
        import psutil
        self.responses = queue.Queue()
        self.cancelled = threading.Event()
        self.request_lock = threading.Lock()
        self.state_lock = threading.RLock()
        self.close_lock = threading.Lock()
        self.closed = False
        self.stderr = (output/'worker.log').open('w', encoding='utf-8')
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        command = [str(args.worker), str(args.model), str(corpus),
            'gpu' if args.device == 'vulkan' else 'cpu', str(args.threads),
            str(corpus/'prompt.txt'), str(args.fallback)]
        options = dict(prompt_space=getattr(args, 'prompt_space', False),
            flash_attn=not getattr(args, 'no_flash_attn', False),
            no_timestamps=getattr(args, 'no_timestamps', False))
        if getattr(args, 'beam_size', 5) != 5:
            options['beam_size'] = args.beam_size
        if getattr(args, 'owner_watch', False):
            options['owner_pid'] = os.getpid()
        if getattr(args, 'decoder_trace', False):
            options['trace_tokens'] = True
        if getattr(args, 'renormalize_timestamps', False):
            options['renormalize_timestamps'] = True
        if getattr(args, 'prompt_token_ids', None) is not None:
            options['prompt_token_ids'] = args.prompt_token_ids
        if getattr(args, 'pool_sample_limit', None) is not None:
            options['pool_sample_limit'] = args.pool_sample_limit
        for name in ('finish_at_eot', 'rank_eot', 'deduplicate_first_step', 'deterministic_topk', 'finished_pool'):
            if getattr(args, name, False): options[name] = True
        # Keep the original seven-argument invocation compatible with saved workers.
        if options['prompt_space'] or not options['flash_attn'] or options['no_timestamps'] or any(key in options for key in ('owner_pid','beam_size','trace_tokens','renormalize_timestamps','prompt_token_ids','finish_at_eot','rank_eot','deduplicate_first_step','deterministic_topk','finished_pool','pool_sample_limit')):
            command.append(json.dumps(options))
        try:
            self.process = subprocess.Popen(command,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
                encoding='utf-8', creationflags=flags)
            self.owner = psutil.Process(self.process.pid)
            self.created = self.owner.create_time()
        except Exception:
            # Popen still owns the original child handle / unreaped child.
            process = getattr(self, 'process', None)
            if process:
                if process.poll() is None: process.kill()
                process.wait(timeout=5)
                if process.stdin: process.stdin.close()
                if process.stdout: process.stdout.close()
            self.stderr.close()
            raise
        self.peak_rss = 0
        self.peak_working_set = 0
        self.monitor_stop = threading.Event()
        def monitor():
            while not self.monitor_stop.wait(.02):
                try:
                    if not self.owner.is_running(): return
                    info = self.owner.memory_info()
                    self.peak_rss = max(self.peak_rss, info.rss)
                    self.peak_working_set = max(self.peak_working_set, getattr(info, 'peak_wset', info.rss))
                except psutil.NoSuchProcess: return
        def reader():
            try:
                for line in self.process.stdout:
                    self.responses.put(json.loads(line))
            except Exception as error: self.responses.put(error)
            finally: self.responses.put(None)
        self.monitor_thread = threading.Thread(target=monitor, daemon=True)
        self.reader_thread = threading.Thread(target=reader, daemon=True)
        self.monitor_thread.start(); self.reader_thread.start()
        try:
            self.ready = self.receive(120)
            if self.ready.get('event') != 'ready': raise RuntimeError('Worker did not load')
            for name in ('finish_at_eot', 'rank_eot'):
                if getattr(args, name, False) and self.ready.get('candidate_completion', {}).get(name) is not True:
                    raise RuntimeError('Worker did not enable requested completion experiment')
            if getattr(args, 'deduplicate_first_step', False) and self.ready.get('deduplicate_first_step') is not True:
                raise RuntimeError('Worker did not enable first-step deduplication')
            if getattr(args, 'deterministic_topk', False) and self.ready.get('deterministic_topk') is not True:
                raise RuntimeError('Worker did not enable deterministic top-k')
            if getattr(args, 'finished_pool', False) and self.ready.get('finished_pool', {}).get('enabled') is not True:
                raise RuntimeError('Worker did not enable finished pool')
            if getattr(args, 'pool_sample_limit', None) is not None and self.ready.get('finished_pool', {}).get('sample_limit') != args.pool_sample_limit:
                raise RuntimeError('Worker did not enable pool sample limit')
            if getattr(args, 'prompt_token_ids', None) is not None:
                if self.ready.get('prompt_tokens', {}).get('source') != 'provided' or self.ready['prompt_tokens']['ids'] != args.prompt_token_ids:
                    raise RuntimeError('Worker did not accept exact prompt token IDs')
            if getattr(args, 'owner_watch', False) and self.ready.get('owner_monitor', {}).get('pid') != os.getpid():
                raise RuntimeError('Worker did not bind its owner')
        except Exception:
            self.close(force=True)
            raise

    def receive(self, timeout):
        result = self.responses.get(timeout=timeout)
        if not isinstance(result, dict): raise RuntimeError('Worker exited or malformed output')
        return result

    def transcribe(self, row, timeout_ms=120000):
        if not self.request_lock.acquire(blocking=False):
            return dict(id=row['id'], error='busy')
        try:
            with self.state_lock:
                if self.cancelled.is_set(): return dict(id=row['id'], error='cancelled')
                if self.closed or self.process.poll() is not None:
                    return dict(id=row['id'], error='worker_stopped')
                self.process.stdin.write(json.dumps(dict(id=row['id'], pcm=row['pcm'], timeout_ms=timeout_ms))+'\n')
                self.process.stdin.flush()
            try:
                result = self.receive(timeout_ms/1000+.25)
            except queue.Empty:
                # The cooperative callback can be deferred until the encoder ends.
                self.close(force=True)
                return dict(id=row['id'], error='timeout', worker_stopped=True)
            except RuntimeError:
                if self.cancelled.is_set(): return dict(id=row['id'], error='cancelled', worker_stopped=True)
                raise
            if self.cancelled.is_set(): return dict(id=row['id'], error='cancelled', worker_stopped=True)
            if result.get('id') != row['id']: raise RuntimeError('Mismatched response')
            return result
        except (OSError, ValueError):
            if self.cancelled.is_set(): return dict(id=row['id'], error='cancelled', worker_stopped=True)
            raise
        finally:
            self.request_lock.release()

    def kill_owned(self):
        with self.state_lock:
            if self.process.poll() is None and self.owner.is_running() and self.owner.create_time() == self.created:
                self.process.kill()
                return True
            return False

    def cancel(self):
        # A cancelled worker is discarded; a new worker loads a clean context.
        with self.state_lock:
            self.cancelled.set()
            self.monitor_stop.set()
            return self.kill_owned()

    def wait_owned(self, timeout):
        # Serialise reaping with kill_owned. An exited Unix child keeps its PID
        # until it is reaped; another client thread cannot reap it mid-kill.
        deadline = time.monotonic()+timeout
        while True:
            with self.state_lock:
                code = self.process.poll()
            if code is not None: return code
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(self.process.args, timeout)
            time.sleep(.01)

    def close(self, force=False):
        with self.close_lock:
            if self.closed: return
            with self.state_lock:
                self.closed = True
                if self.request_lock.locked():
                    self.cancelled.set()
                    force = True
                if force: self.kill_owned()
                self.monitor_stop.set()
                if self.process.stdin and not self.process.stdin.closed:
                    try: self.process.stdin.close()
                    except OSError: pass
            try:
                self.wait_owned(15)
            except subprocess.TimeoutExpired:
                self.kill_owned()
                self.wait_owned(15)
            self.monitor_thread.join(timeout=1)
            self.reader_thread.join(timeout=1)
            self.process.stdout.close()
            self.stderr.close()


def run(args, corpus, output):
    import numpy as np
    import psutil
    manifest = json.loads((corpus/'manifest.json').read_text(encoding='utf-8'))
    selected = manifest['samples']
    if args.limit: selected = selected[:args.limit]
    if args.ids: selected = [s for s in selected if s['id'] in args.ids]
    isolated(corpus/'source/backend')
    import speech_to_text as stt
    import check_recognition
    import accuracy_voice
    import browser_commands
    import understanding
    from voice_name_trigger import check_voice_trigger
    from command_parser import CommandParser
    from fast_intent import get_fast_intent_engine
    from question_answerer import get_question_answerer
    engines = dict(intent_engine=get_fast_intent_engine(), parser=CommandParser(), answerer=get_question_answerer())
    def decide(text):
        trigger = check_voice_trigger(text)
        if not trigger.has_trigger: return None
        command = trigger.command_text
        if command.casefold().strip(' .,!?:') in ('стоп', 'хватит', 'замолчи', 'достаточно'):
            return understanding.Decision(kind='interrupt')
        browser = browser_commands.parse(command)
        return understanding.Decision(kind='browser', parsed=browser) if browser else understanding.understand(command, **engines)
    native = None
    model_copy = output/'model-input'
    output.mkdir(parents=True)
    ready = {}
    rows = []
    try:
        if args.engine == 'cpp':
            native = Native(args, corpus, output)
            ready = native.ready
        else:
            # Copy before guard would be needed for a model in protected backend/data.
            # The caller must supply a separate experimental checkpoint.
            import torch
            torch.set_num_threads(args.threads)
            stt._подсказка = lambda: (corpus/'prompt.txt').read_text(encoding='utf-8')
            model_copy.mkdir()
            checkpoint = model_copy/('large-v3-turbo.pt' if args.model_name == 'turbo' else 'small.pt')
            shutil.copy2(args.model, checkpoint)
            recognizer = stt.Recognizer(args.model_name, args.device)
            started = time.perf_counter()
            import whisper
            recognizer._model = whisper.load_model(str(checkpoint), device=args.device)
            recognizer.engine = 'openai'
            ready = dict(load_seconds=time.perf_counter()-started, threads=args.threads)
            if args.device == 'cuda': torch.cuda.reset_peak_memory_stats()
        # Keep provenance even if the shell/session is interrupted before result.json.
        write_json(output/'run.json', dict(engine=args.engine, device=args.device,
            model=args.model_name, ready=ready, model_sha256=sha(args.model),
            worker_sha256=sha(args.worker) if native else None,
            prompt_token_file_sha256=sha(args.prompt_tokens) if getattr(args, 'prompt_tokens', None) else None))
        for repeat in range(args.repeats):
            for sample in selected:
                assert sha(corpus/sample['pcm']) == sample['sha256']
                expected = decide(sample['reference'])
                started = time.perf_counter()
                if args.engine == 'cpp':
                    result = dict(text='', seconds=0, gated=True) if sample['gated'] else native.transcribe(sample)
                    if result.get('error'): raise RuntimeError(f"Decode error {sample['id']}: {result['error']}")
                    heard = result['text'].strip()
                    if stt.looks_like_hallucination(heard): heard = ''
                else:
                    torch.manual_seed(1243)
                    heard = recognizer.transcribe(np.fromfile(corpus/sample['raw'], dtype='<f4'))
                    result = dict(seconds=time.perf_counter()-started)
                elapsed = time.perf_counter()-started
                actual = decide(heard)
                correct = actual is None if expected is None else accuracy_voice._same_decision(expected, actual)
                rows.append(dict(**sample, repeat=repeat, heard=heard, correct=correct,
                    unexpected_activation=expected is None and actual is not None,
                    seconds=elapsed, decode_seconds=result['seconds'],
                    native_result=result if native else None,
                    wer=check_recognition.word_error_rate(check_recognition.words(sample['reference']), check_recognition.words(heard))))
                write_json(output/'partial.json', rows)
                if len(rows) % 8 == 0: print(json.dumps(dict(done=len(rows), total=len(selected)*args.repeats)), flush=True)
        memory = dict(peak_worker_rss=native.peak_rss, process_peak_working_set=native.peak_working_set) if native else dict(
            process_peak_working_set=psutil.Process().memory_info().peak_wset if os.name == 'nt' else psutil.Process().memory_info().rss,
            torch_cuda_peak_allocated=torch.cuda.max_memory_allocated() if args.device == 'cuda' else 0,
            torch_cuda_peak_reserved=torch.cuda.max_memory_reserved() if args.device == 'cuda' else 0)
        summary = []
        for corpus_name in sorted({r['corpus'] for r in rows}):
            for condition in sorted({r['condition'] for r in rows if r['corpus'] == corpus_name}):
                chosen = [r for r in rows if (r['corpus'], r['condition']) == (corpus_name, condition)]
                warm = [r['seconds'] for r in chosen if r is not rows[0]]
                summary.append(dict(corpus=corpus_name, condition=condition, count=len(chosen),
                    correct=sum(r['correct'] for r in chosen), unexpected_activations=sum(r['unexpected_activation'] for r in chosen),
                    mean_wer=statistics.mean(r['wer'] for r in chosen), median_seconds=statistics.median(warm or [r['seconds'] for r in chosen])))
        report = dict(engine=args.engine, device=args.device, model=args.model_name, model_sha256=sha(args.model),
            worker_sha256=sha(args.worker) if native else None,
            ready=ready, memory=memory, summary=summary, rows=rows,
            microphone_used=False, playback_used=False, commands_executed=False,
            cpp_temperature_increment=args.fallback if native else None,
            prompt_token_file_sha256=sha(args.prompt_tokens) if getattr(args, 'prompt_tokens', None) else None,
            cpp_short_loop_retry=False if native else None)
        write_json(output/'result.json', report)
        print(json.dumps(dict(summary=summary, memory=memory)), flush=True)
    finally:
        if native: native.close()
        if model_copy.exists():
            assert model_copy.resolve().is_relative_to(output)
            shutil.rmtree(model_copy)


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'): stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('op', choices=('prepare', 'run'))
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--engine', choices=('cpp', 'python'), default='cpp')
    parser.add_argument('--device', choices=('cpu', 'cuda', 'vulkan'), default='cpu')
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--model', type=Path)
    parser.add_argument('--model-name', choices=('small', 'turbo'), default='turbo')
    parser.add_argument('--threads', type=int, default=8)
    parser.add_argument('--fallback', type=float, choices=(0, .2), default=.2)
    parser.add_argument('--prompt-space', action='store_true')
    parser.add_argument('--no-flash-attn', action='store_true')
    parser.add_argument('--no-timestamps', action='store_true')
    parser.add_argument('--beam-size', type=int, choices=range(1, 9), default=5,
        help='Native beam search width; pinned upstream supports at most 8')
    parser.add_argument('--owner-watch', action='store_true', help='Require the worker to bind this parent process')
    parser.add_argument('--decoder-trace', action='store_true', help='Collect bounded diagnostics from a trace build')
    parser.add_argument('--renormalize-timestamps', action='store_true', help='Diagnostic copy only: normalize after timestamp masks')
    parser.add_argument('--prompt-tokens', type=Path, help='Diagnostic worker only: exact ordinary token IDs in a reports JSON file')
    parser.add_argument('--finish-at-eot', action='store_true', help='Diagnostic copy: finish candidates at sampled EOT')
    parser.add_argument('--rank-eot', action='store_true', help='Diagnostic copy: include sampled trailing EOT in rank score')
    parser.add_argument('--deduplicate-first-step', action='store_true', help='Diagnostic copy: avoid identical initial beam candidates')
    parser.add_argument('--deterministic-topk', action='store_true', help='Diagnostic copy: select sorted logits instead of random draws')
    parser.add_argument('--finished-pool', action='store_true', help='Diagnostic copy: zero-temperature beam with separate finished candidates')
    parser.add_argument('--pool-sample-limit', type=int, choices=range(1,221), help='Diagnostic pool only: force a bounded early finalization')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--ids', type=int, nargs='+')
    parser.add_argument('--repeats', type=int, default=1)
    args = parser.parse_args()
    if (args.finish_at_eot or args.rank_eot or args.deduplicate_first_step or args.deterministic_topk or args.finished_pool) and (args.engine != 'cpp' or args.op != 'run'):
        parser.error('Completion experiments require a C++ run')
    if args.finished_pool and (args.finish_at_eot or args.rank_eot or args.deduplicate_first_step or args.deterministic_topk):
        parser.error('Finished pool cannot combine with the earlier completion/topk flags')
    if args.pool_sample_limit is not None and not args.finished_pool:
        parser.error('Pool sample limit requires --finished-pool')
    args.prompt_token_ids = None
    if args.prompt_tokens is not None:
        if args.engine != 'cpp' or args.op != 'run' or args.prompt_space:
            parser.error('Exact prompt tokens require a C++ run without --prompt-space')
        try: args.prompt_token_ids = read_prompt_tokens(args.prompt_tokens)
        except (ValueError, OSError): parser.error('Invalid experimental prompt token file')
    for name in ('corpus', 'output', 'worker', 'model', 'prompt_tokens'):
        path = getattr(args, name)
        if path is not None: setattr(args, name, path.resolve())
    if not args.corpus.is_relative_to(ROOT/'reports'): parser.error('Corpus must be inside reports')
    if args.op == 'prepare':
        if args.corpus.exists(): parser.error('Choose a new corpus directory')
        prepare(args.corpus)
    else:
        if not args.output or not args.output.is_relative_to(ROOT/'reports') or args.output.exists():
            parser.error('Choose a new output directory inside reports')
        if not args.model or not args.model.is_file(): parser.error('An existing model is required')
        if args.engine == 'cpp' and (not args.worker or not args.worker.is_file()): parser.error('Worker required')
        run(args, args.corpus, args.output)


if __name__ == '__main__': main()
