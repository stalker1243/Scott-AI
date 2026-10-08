"""Optional Scott Voice process client. Importing it never loads a speech model."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from queue import Queue, Empty, Full
import hashlib
import json
import os
import subprocess
import threading
import time
import uuid
import wave
import psutil
try:
    from .voice_cache import touch as touch_cache, prune as prune_cache
except ImportError:
    from voice_cache import touch as touch_cache, prune as prune_cache

PROTOCOL = 1
MAX_TEXT = 1200
MAX_STREAM_CHUNKS = 128
PROFILES = ('natural', 'restrained', 'scott', 'digital')


def watch_owner():
    """Called by the worker: release it even if the API process was killed."""
    try:
        owner = psutil.Process(int(os.environ['SCOTT_VOICE_OWNER_PID']))
        created = float(os.environ['SCOTT_VOICE_OWNER_CREATED'])
        if abs(owner.create_time()-created) > .01:
            os._exit(0)
    except (KeyError, ValueError, psutil.AccessDenied):
        return
    except psutil.NoSuchProcess:
        os._exit(0)
    def monitor():
        while True:
            time.sleep(.5)
            try:
                if not owner.is_running() or owner.status() == psutil.STATUS_ZOMBIE:
                    os._exit(0)
            except psutil.NoSuchProcess:
                os._exit(0)
            except psutil.AccessDenied:
                return
    threading.Thread(target=monitor, daemon=True, name='voice-owner-watch').start()


class VoiceProcessError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__('Scott Voice: '+code)


def stop_process_tree(process, owner=None):
    """Terminate only descendants captured from this owned subprocess."""
    descendants = []
    try:
        if owner and owner.is_running():
            descendants = owner.children(recursive=True)
    except psutil.NoSuchProcess:
        pass
    for child in reversed(descendants):
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(descendants, timeout=3)
    for child in alive:
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass
    if alive:
        psutil.wait_procs(alive, timeout=3)
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def checksum(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class VoiceProcessConfig:
    python: Path
    worker: Path
    model_dir: Path
    reference_json: Path
    profiles_json: Path
    cache_dir: Path
    device: str = 'cuda'
    cpu_threads: int = 4
    rms_norm: bool = False
    cache_max_bytes: int = 512*1024*1024
    cache_max_entries: int = 1000

    def wire(self):
        if self.device not in ('cuda','cpu') or not 1 <= self.cpu_threads <= 16:
            raise ValueError('Invalid device or CPU thread count')
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 1
               for value in (self.cache_max_bytes, self.cache_max_entries)):
            raise ValueError('Invalid voice cache budget')
        # A venv executable can be a symlink. Resolve it and Python loses the
        # pyvenv.cfg beside the invoked path, along with installed dependencies.
        return {name: str(value.absolute() if name == 'python' else value.resolve()) if isinstance(value,Path) else value
                for name,value in self.__dict__.items()}

    @classmethod
    def from_wire(cls, value):
        return cls(**{name:Path(item) if name.endswith('_dir') or name.endswith('_json')
                       or name in ('python','worker') else item for name,item in value.items()})


def recipe_id(config):
    """Invalidate audio when its reference, model revision, DSP or recipe changes."""
    reference = json.loads(config.reference_json.read_text(encoding='utf-8'))
    reference_audio = config.reference_json.parent/'scott-reference.wav'
    if checksum(reference_audio) != reference['sha256']:
        raise ValueError('Selected voice reference hash mismatch')
    manifest = json.loads((config.model_dir/'scott-model.json').read_text(encoding='utf-8'))
    processor = config.worker.parent/'create_scott_voice.py'
    recipe = dict(protocol=PROTOCOL, model=manifest['model'], revision=manifest['revision'],
                  reference=checksum(config.reference_json), profiles=checksum(config.profiles_json),
                  worker=checksum(config.worker), client=checksum(__file__),
                  processor=checksum(processor) if processor.is_file() else None,
                  stream_processor=checksum(config.worker.parent/'stream_voice.py')
                      if (config.worker.parent/'stream_voice.py').is_file() else None,
                  formatter=checksum(Path(__file__).with_name('speech_text.py')),
                  device=config.device, cpu_threads=config.cpu_threads, rms_norm=config.rms_norm,
                  python=str(config.python.resolve()), seed=20261006, language='Russian',
                  max_new_tokens=768, temperature=.7, top_p=.95, subtalker_temperature=.7)
    return hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest()


def audio_key(recipe, text, profile):
    return hashlib.sha256(json.dumps([recipe,text,profile],ensure_ascii=False).encode('utf-8')).hexdigest()


def cache_path(directory, key):
    if len(key)!=64 or any(character not in '0123456789abcdef' for character in key):
        raise ValueError('Invalid audio cache key')
    return Path(directory)/('scott-voice-'+key+'.wav')


def cached_audio(directory, key):
    path = cache_path(directory,key)
    try:
        metadata = json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
        if metadata.get('protocol') != PROTOCOL or metadata.get('key') != key or checksum(path) != metadata.get('sha256'):
            return None
        with wave.open(str(path),'rb') as audio:
            frames,rate = audio.getnframes(),audio.getframerate()
            if audio.getnchannels()!=1 or audio.getsampwidth()!=2 or rate!=24000 or not frames:
                return None
            payload = audio.readframes(frames)
            if len(payload)!=frames*2 or not any(payload):
                return None
        touch_cache(path)
        return dict(path=str(path.resolve()),seconds=round(frames/rate,3))
    except (OSError,ValueError,KeyError,TypeError,wave.Error,EOFError):
        return None


def publish_audio(directory, key, request, temporary):
    """Commit a complete WAV and its checksum; metadata contains no speech text."""
    destination = cache_path(directory,key)
    with wave.open(str(temporary),'rb') as audio:
        if audio.getnchannels()!=1 or audio.getsampwidth()!=2 or audio.getframerate()!=24000 or not audio.getnframes():
            raise ValueError('Invalid worker WAV')
    metadata = dict(protocol=PROTOCOL,key=key,sha256=checksum(temporary))
    pending = Path(directory)/f'.pending-{request}.json'
    pending.write_text(json.dumps(metadata,sort_keys=True),encoding='utf-8')
    os.replace(temporary,destination)
    os.replace(pending,destination.with_suffix('.json'))


@dataclass(frozen=True)
class VoiceAudio:
    path: str
    cached: bool
    seconds: float


def stream_path(directory, request, sequence):
    if not isinstance(request,str) or len(request)!=32 or any(c not in '0123456789abcdef' for c in request) or isinstance(sequence,bool) \
            or not isinstance(sequence,int) or not 0<=sequence<MAX_STREAM_CHUNKS:
        raise VoiceProcessError('invalid_protocol')
    return Path(directory)/f'.stream-{request}-{sequence:03}.wav'


def stream_audio(directory, request, sequence, packet):
    path=stream_path(directory,request,sequence)
    try:
        if path.is_symlink() or checksum(path)!=packet.get('sha256'):
            raise ValueError('Invalid chunk identity')
        with wave.open(str(path),'rb') as audio:
            frames=audio.getnframes()
            if audio.getnchannels()!=1 or audio.getsampwidth()!=2 or audio.getframerate()!=24000 \
                    or not 0<frames<=120000 or len(audio.readframes(frames))!=frames*2:
                raise ValueError('Invalid chunk format')
        return VoiceAudio(str(path.resolve()),False,frames/24000),frames
    except (OSError,ValueError,wave.Error,EOFError):
        raise VoiceProcessError('invalid_audio') from None


class ScottVoiceProcess:
    """Serial requests, verified persistent audio and a replaceable isolated worker."""
    def __init__(self, config, *, timeout=90, startup_timeout=45, idle_timeout=120, prepare_timeout=180):
        if min(timeout,startup_timeout,prepare_timeout)<=0 or idle_timeout<0:
            raise ValueError('Invalid worker timeouts')
        self.config = config
        config.wire()
        self.recipe = recipe_id(config)
        self.timeout,self.startup_timeout,self.idle_timeout = timeout,startup_timeout,idle_timeout
        self.prepare_timeout = prepare_timeout
        self._request_lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._worker = None
        self._generation = 0
        self._closed = False
        self._idle_timer = None
        self._active = False
        self._features = set()
        self._prepared = False

    def status(self):
        with self._state_lock:
            process = self._worker[0] if self._worker else None
            return dict(running=bool(process and process.poll() is None),
                        pid=process.pid if process and process.poll() is None else None,
                        active=self._active,closed=self._closed,
                        model_loaded=bool(process and process.poll() is None and self._prepared))

    def _check_generation(self, generation):
        if self._closed:
            raise VoiceProcessError('closed')
        if generation != self._generation:
            raise VoiceProcessError('cancelled')

    @staticmethod
    def _read_protocol(stream, messages):
        try:
            while True:
                line = stream.readline(65537)
                if not line:
                    break
                if len(line)>65536 or not line.endswith('\n'):
                    messages.put_nowait(dict(event='error',code='invalid_protocol'))
                    break
                value = json.loads(line)
                if not isinstance(value,dict):
                    raise ValueError('Expected object')
                messages.put_nowait(value)
        except (OSError,ValueError,Full):
            pass
        finally:
            try:
                messages.put_nowait(None)
            except Full:
                pass
            stream.close()

    @staticmethod
    def _drain_errors(stream):
        # Libraries can print during import. Their output never enters JSON IPC
        # or the user's conversation; drain it without collecting personal text.
        try:
            while stream.read(4096):
                pass
        finally:
            stream.close()

    def _wait(self, worker, generation, timeout):
        process,messages = worker[:2]
        deadline = time.monotonic()+timeout
        while True:
            with self._state_lock:
                self._check_generation(generation)
            remaining = deadline-time.monotonic()
            if remaining<=0:
                raise VoiceProcessError('timeout')
            try:
                value = messages.get(timeout=min(.1,remaining))
            except Empty:
                with self._state_lock:
                    self._check_generation(generation)
                if process.poll() is not None:
                    raise VoiceProcessError('worker_exited')
                continue
            with self._state_lock:
                self._check_generation(generation)
            if value is None:
                raise VoiceProcessError('worker_exited')
            if value.get('event')=='error':
                raise VoiceProcessError(value.get('code','synthesis_failed'))
            return value

    def _start(self, generation):
        with self._state_lock:
            self._check_generation(generation)
            if self._worker and self._worker[0].poll() is None:
                return self._worker
            if self._worker:
                self._dispose(self._worker)
                self._worker = None
            self.config.cache_dir.mkdir(parents=True,exist_ok=True)
            env = dict(os.environ)
            for name in list(env):
                if name.endswith('_API_KEY') or name.endswith('_TOKEN') or name in ('HF_TOKEN','HUGGING_FACE_HUB_TOKEN'):
                    env.pop(name,None)
            env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_IMPLICIT_TOKEN='1',
                       PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',
                       SCOTT_VOICE_OWNER_PID=str(os.getpid()),
                       SCOTT_VOICE_OWNER_CREATED=str(psutil.Process().create_time()))
            try:
                process = subprocess.Popen([str(self.config.python),'-u',str(self.config.worker),
                    '--configuration',json.dumps(self.config.wire(),ensure_ascii=False)],
                    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                    text=True,encoding='utf-8',errors='replace',bufsize=1,env=env,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            except OSError as error:
                raise VoiceProcessError('start_failed') from error
            try:
                owner = psutil.Process(process.pid)
            except psutil.NoSuchProcess:
                owner = None
            # A prepared profile can emit all blocks before the consumer reads
            # them. Bound memory by one complete utterance plus control packets.
            worker = process,Queue(maxsize=MAX_STREAM_CHUNKS+2),owner
            self._worker = worker
            self._prepared = False
            threading.Thread(target=self._read_protocol,args=(process.stdout,worker[1]),daemon=True).start()
            threading.Thread(target=self._drain_errors,args=(process.stderr,),daemon=True).start()
        ready = self._wait(worker,generation,self.startup_timeout)
        if ready.get('event')!='ready' or ready.get('protocol')!=PROTOCOL or ready.get('recipe')!=self.recipe:
            raise VoiceProcessError('invalid_protocol')
        features=ready.get('features',[])
        if not isinstance(features,list) or len(features)>16 or any(not isinstance(v,str) for v in features):
            raise VoiceProcessError('invalid_protocol')
        self._features=set(features)
        return worker

    def _dispose(self, worker):
        if not worker:
            return
        process = worker[0]
        # Windows venv redirectors can run the real Python as a descendant.
        # Stop owned descendants first so cancellation also frees the GPU.
        stop_process_tree(process, worker[2])
        if process.stdin:
            process.stdin.close()

    def cancel(self):
        with self._state_lock:
            self._generation += 1
            worker,self._worker = self._worker,None
            if self._idle_timer:
                self._idle_timer.cancel()
                self._idle_timer = None
        self._dispose(worker)

    def close(self):
        with self._state_lock:
            self._closed = True
        self.cancel()

    def _expire_idle(self, worker):
        if not self._request_lock.acquire(blocking=False):
            return
        try:
            with self._state_lock:
                if self._worker is not worker or self._active:
                    return
                self._worker = None
            self._dispose(worker)
            prune_cache(self.config.cache_dir, self.config.cache_max_bytes, self.config.cache_max_entries)
        finally:
            self._request_lock.release()

    def _maintain_cache(self, current, force=False):
        # Cache retrieval stays cheap; scan the directory at most once a minute
        # on hits, and after publishing a newly generated file.
        if force or time.monotonic() >= getattr(self, '_prune_due', 0):
            prune_cache(self.config.cache_dir, self.config.cache_max_bytes, self.config.cache_max_entries,
                        protected=[current])
            self._prune_due = time.monotonic()+60

    def stream(self, text, profile, on_audio, on_abort=None):
        if not callable(on_audio) or (on_abort is not None and not callable(on_abort)):
            raise ValueError('Expected stream callbacks')
        return self.synthesize(text,profile,on_audio=on_audio,on_abort=on_abort)

    def prepare(self):
        """Load the model and accepted prompt, without generating or playing speech."""
        with self._state_lock:
            generation = self._generation
            self._check_generation(generation)
        with self._request_lock:
            with self._state_lock:
                self._check_generation(generation)
                self._active = True
                if self._idle_timer:
                    self._idle_timer.cancel()
                    self._idle_timer = None
            try:
                worker = self._start(generation)
                if 'prepare_v1' not in self._features:
                    raise VoiceProcessError('prepare_unavailable')
                request = uuid.uuid4().hex
                packet = dict(id=request, action='prepare', recipe=self.recipe)
                worker[0].stdin.write(json.dumps(packet)+'\n')
                worker[0].stdin.flush()
                reply = self._wait(worker,generation,self.prepare_timeout)
                if reply.get('event')!='prepared' or reply.get('id')!=request or reply.get('recipe')!=self.recipe:
                    raise VoiceProcessError('invalid_protocol')
                with self._state_lock:
                    self._check_generation(generation)
                    self._prepared = True
            except Exception as error:
                with self._state_lock:
                    failed = self._worker if self._generation==generation else None
                    if failed:
                        self._worker = None
                self._dispose(failed)
                if isinstance(error,VoiceProcessError):
                    raise
                raise VoiceProcessError('worker_exited') from error
            finally:
                with self._state_lock:
                    self._active = False
                    if self._worker and self.idle_timeout and not self._closed:
                        self._idle_timer = threading.Timer(self.idle_timeout,self._expire_idle,args=(self._worker,))
                        self._idle_timer.daemon = True
                        self._idle_timer.start()
            return self.status()

    def synthesize(self, text, profile='scott', *, on_audio=None, on_abort=None):
        if not isinstance(text,str) or not text.strip() or len(text)>MAX_TEXT or profile not in PROFILES:
            raise ValueError('Invalid speech text or profile')
        try:
            from .speech_text import prepare_for_speech
        except ImportError:
            from speech_text import prepare_for_speech
        prepared = prepare_for_speech(text,accents=False).strip()
        if not prepared or len(prepared)>MAX_TEXT:
            raise ValueError('Empty or excessive prepared speech text')
        key = audio_key(self.recipe,prepared,profile)
        with self._state_lock:
            generation = self._generation
            self._check_generation(generation)
        with self._request_lock:
            request = uuid.uuid4().hex
            worker = None
            sequence,stream_frames,last_chunk = 0,0,False
            delivered=False
            with self._state_lock:
                self._check_generation(generation)
                self._active = True
                if self._idle_timer:
                    self._idle_timer.cancel()
                    self._idle_timer = None
            try:
                cached = cached_audio(self.config.cache_dir,key)
                if cached:
                    self._maintain_cache(cached['path'])
                    audio=VoiceAudio(**cached,cached=True)
                    if on_audio is not None:
                        delivered=True
                        on_audio(audio,True)
                    with self._state_lock:
                        self._check_generation(generation)
                    return audio
                worker = self._start(generation)
                if on_audio is not None and 'stream_v1' not in self._features:
                    raise VoiceProcessError('stream_unavailable')
                packet = dict(id=request,action='stream' if on_audio is not None else 'synthesize',text=prepared,profile=profile,key=key)
                worker[0].stdin.write(json.dumps(packet,ensure_ascii=False)+'\n')
                worker[0].stdin.flush()
                deadline=time.monotonic()+self.timeout
                while True:
                    if time.monotonic()>=deadline:
                        raise VoiceProcessError('timeout')
                    reply = self._wait(worker,generation,deadline-time.monotonic())
                    if reply.get('event')!='chunk':
                        break
                    if on_audio is None or last_chunk or reply.get('id')!=request or reply.get('key')!=key \
                            or reply.get('sequence')!=sequence or isinstance(reply.get('sequence'),bool) \
                            or not isinstance(reply.get('last'),bool):
                        raise VoiceProcessError('invalid_protocol')
                    audio,frames=stream_audio(self.config.cache_dir,request,sequence,reply)
                    last_chunk=reply['last']
                    sequence+=1; stream_frames+=frames
                    started=time.monotonic()
                    delivered=True
                    on_audio(audio,last_chunk)
                    deadline+=time.monotonic()-started
                if reply.get('event')!='audio' or reply.get('id')!=request or reply.get('key')!=key:
                    raise VoiceProcessError('invalid_protocol')
                if on_audio is not None and not last_chunk:
                    raise VoiceProcessError('invalid_protocol')
                cached = cached_audio(self.config.cache_dir,key)
                if not cached:
                    raise VoiceProcessError('invalid_audio')
                if on_audio is not None:
                    with wave.open(cached['path'],'rb') as full:
                        if full.getnframes()!=stream_frames:
                            raise VoiceProcessError('invalid_audio')
                with self._state_lock:
                    self._check_generation(generation)
                    self._prepared = reply.get('model_loaded') is True
                self._maintain_cache(cached['path'], force=True)
                return VoiceAudio(**cached,cached=bool(reply.get('cached',False)))
            except Exception as error:
                if delivered and on_abort is not None:
                    try:
                        on_abort()
                    except Exception:
                        pass
                with self._state_lock:
                    failed = self._worker if self._generation==generation else None
                    if failed:
                        self._worker = None
                self._dispose(failed)
                if isinstance(error,VoiceProcessError):
                    raise
                raise VoiceProcessError('worker_exited') from error
            finally:
                for part in self.config.cache_dir.glob(f'.stream-{request}-*'):
                    if part.suffix in ('.wav','.tmp'):
                        try:
                            part.unlink(missing_ok=True)
                        except OSError:
                            pass
                for suffix in ('.wav','.json'):
                    try:
                        (self.config.cache_dir/f'.pending-{request}{suffix}').unlink(missing_ok=True)
                    except OSError:
                        pass
                with self._state_lock:
                    self._active = False
                    if self._worker and self.idle_timeout and not self._closed:
                        self._idle_timer = threading.Timer(self.idle_timeout,self._expire_idle,args=(self._worker,))
                        self._idle_timer.daemon = True
                        self._idle_timer.start()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
