"""Local Scott Voice engine; models and Torch stay in the child process."""
from __future__ import annotations

import atexit
from dataclasses import replace
from contextlib import contextmanager
from concurrent.futures import Future
from functools import lru_cache, wraps
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import textwrap
import psutil
try:
    from .performance_trace import measured, phase
except ImportError:
    from performance_trace import measured, phase

try:
    from .scott_voice_sdk import VERSIONS as SDK_VERSIONS
except ImportError:
    from scott_voice_sdk import VERSIONS as SDK_VERSIONS

try:
    from .scott_voice_process import ScottVoiceProcess, VoiceProcessConfig, VoiceProcessError, recipe_id, stop_process_tree, PYTHON_OPTIONS, runtime_environment
except ImportError:
    from scott_voice_process import ScottVoiceProcess, VoiceProcessConfig, VoiceProcessError, recipe_id, stop_process_tree, PYTHON_OPTIONS, runtime_environment

VOICE_ID = 'scott-voice'
ROOT = Path(__file__).resolve().parent.parent
PROFILES = {
    'natural': 'Исходный — уверенный и сдержанный',
    'restrained': 'Сдержанный — лёгкая цифровая окраска',
    'scott': 'Scott — умеренная цифровая окраска',
    'digital': 'Цифровой — выраженный машинный тембр',
}
MESSAGES = {
    'not_installed': 'Scott Voice не установлен. Установите компонент в настройках голоса; чат доступен.',
    'invalid_assets': 'Файлы Scott Voice неполные или повреждены.',
    'runtime_unavailable': 'Окружение Scott Voice недоступно.',
    'cuda_unavailable': 'Для Scott Voice не найден доступный CUDA GPU. CPU пока экспериментален.',
    'timeout': 'Scott Voice не успел подготовить звук. Повторите попытку или проверьте голос в настройках; ответ доступен в чате.',
    'synthesis_failed': 'Scott Voice не смог подготовить звук. Проверьте голос в настройках; ответ доступен в чате.',
    'runtime_update_required': 'Файлы Scott Voice нужно обновить в настройках голоса.',
    'stream_unavailable': 'Потоковый режим недоступен. Используется обычная озвучка Scott Voice.',
    'prepare_unavailable': 'Для подготовки модели нужно обновить установленный Scott Voice.',
}


def speech_chunks(text, *, short_first=True):
    """Start long replies with a shorter clause; keep all words in playback order."""
    try:
        from .speech_text import prepare_for_speech, split_for_speech
    except ImportError:
        from speech_text import prepare_for_speech, split_for_speech
    prepared = prepare_for_speech(text, accents=False)
    chunks = [part for sentence in split_for_speech(prepared, min_chars=120)
              for part in textwrap.wrap(sentence, width=180, break_long_words=True, break_on_hyphens=False)]
    # Keep short answers whole, including their existing cache key. Split a
    # longer opening at a clause/word boundary, leaving a useful continuation.
    if not short_first or not chunks or len(chunks[0]) <= 110:
        return chunks
    first = chunks[0]
    boundaries = [match.end() for match in re.finditer(r'[,;:](?=\s)|\s[—–](?=\s)', first)
                  if 40 <= match.end() <= 90]
    cut = boundaries[-1] if boundaries else len(textwrap.wrap(first, width=90,
        break_long_words=False, break_on_hyphens=False)[0])
    if cut == len(first):
        return chunks
    return [first[:cut].strip(), first[cut:].strip(), *chunks[1:]]


def _worker_cpu_threads(device, accelerated=False):
    """Keep CUDA's host work small; allow an explicit hardware-specific choice."""
    default = 2 if device=='cuda' and not accelerated else 4
    value = os.getenv('SCOTT_VOICE_CPU_THREADS','auto').strip().lower()
    try:
        threads = int(value)
    except ValueError:
        return default
    return threads if 1<=threads<=16 else default


def config_at(root, cache_root=None):
    experiment = Path(root)/'experiments/voice_design'  # Existing SDK/model layout.
    runtime = Path(root)/'voice/runtime'
    resources = runtime if runtime.is_dir() else experiment
    python = experiment/('.venv/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python')
    device = os.getenv('SCOTT_VOICE_DEVICE', 'cuda').strip().lower()
    return VoiceProcessConfig(python=python, worker=resources/'voice_worker.py',
        model_dir=experiment/'models/base',
        reference_json=Path(root)/'reports/voice-design/reference/reference.json',
        profiles_json=resources/'robotic_profiles.json',
        cache_dir=Path(cache_root or root)/'audio_cache/scott-voice',
        device=device, cpu_threads=_worker_cpu_threads(device))


def default_config(root=ROOT):
    # A separate optional installation takes priority once provisioning is complete.
    # Explicit overrides also report missing/incomplete installations in the catalog.
    override = os.getenv('SCOTT_VOICE_HOME', '').strip()
    try:
        from .scott_voice_install import home_path
    except ImportError:
        from scott_voice_install import home_path
    home = home_path(root)
    def cached(config):
        # Explicit fixture/installer roots retain their public cache contract.
        if Path(root).resolve() == ROOT.resolve():
            try:
                from .storage_paths import audio_cache
            except ImportError:
                from storage_paths import audio_cache
            return replace(config, cache_dir=audio_cache()/'scott-voice')
        return config
    if override:
        return cached(config_at(home, cache_root=root))
    try:
        marker = json.loads((home/'scott-install.json').read_text(encoding='utf-8'))
        ready = isinstance(marker, dict) and marker.get('ready') is True
    except (OSError, ValueError, TypeError):
        ready = False
    return cached(config_at(home if ready else root, cache_root=root))


def preferred_config():
    """Application preferences stay separate from installer/benchmark defaults."""
    try:
        from .voice_config import get_scott_acceleration
    except ImportError:
        from voice_config import get_scott_acceleration
    config=default_config()
    accelerated = get_scott_acceleration() and config.device=='cuda'
    return replace(config,rms_norm=accelerated,
        cpu_threads=_worker_cpu_threads(config.device,accelerated))


_probe_lock = threading.Lock()
_probe_pending = {}
_probe_epoch = 0


@lru_cache(maxsize=4)
def _runtime_probe_result(python, device, fingerprint=None, epoch=0):
    # Probe only in the optional interpreter; never load Qwen in the API process.
    script = ("import importlib.util,importlib.metadata as m,json; "
              "ready=all(importlib.util.find_spec(n) is not None for n in "
              "('torch','qwen_tts','soundfile','scipy')); "
              f"expected={SDK_VERSIONS!r}; versions={{}}\n"
              "for name in expected:\n"
              " try: versions[name]=m.version(name)\n"
              " except m.PackageNotFoundError: pass\n"
              "compatible=versions==expected\n"
              "cuda=False\n"
              "if compatible:\n import torch\n cuda=torch.cuda.is_available()\n"
              "print(json.dumps({'ready':ready,'compatible':compatible,'cuda':cuda}))")
    env = runtime_environment()
    try:
        process = subprocess.Popen([python, *PYTHON_OPTIONS, '-c', script], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            encoding='utf-8', env=env,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            owner = psutil.Process(process.pid)
        except psutil.NoSuchProcess:
            owner = None
        try:
            output, _ = process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            stop_process_tree(process, owner)
            process.communicate(timeout=3)
            return 'runtime_unavailable'
        info = json.loads(output.strip()) if process.returncode == 0 else {}
        if not info.get('ready'):
            return 'runtime_unavailable'
        if not info.get('compatible'):
            return 'runtime_update_required'
        if device == 'cuda' and not info.get('cuda'):
            return 'cuda_unavailable'
        return ''
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 'runtime_unavailable'


def _probe_runtime(python, device, fingerprint=None):
    """Share concurrent native checks; unrelated installations remain independent."""
    with _probe_lock:
        key = (python,device,fingerprint,_probe_epoch)
        pending = _probe_pending.get(key)
        leader = pending is None
        if leader:
            pending = _probe_pending[key] = Future()
    if not leader:
        return pending.result()
    try:
        result = _runtime_probe_result(*key)
    except BaseException as error:
        pending.set_exception(error)
        raise
    else:
        pending.set_result(result)
        return result
    finally:
        with _probe_lock:
            _probe_pending.pop(key,None)


def _clear_runtime_probe():
    global _probe_epoch
    with _probe_lock:
        # An already running check may finish, but a new caller must not join it.
        _probe_epoch += 1
        _runtime_probe_result.cache_clear()


_probe_runtime.cache_clear = _clear_runtime_probe
_probe_runtime.cache_info = _runtime_probe_result.cache_info


def inspect_installation(config):
    # A base update must invalidate readiness even while the expensive probe is cached.
    with _probe_lock:
        epoch = _probe_epoch
    try:
        from .voice_shared_runtime import config_fingerprint, SharedRuntimeError
    except ImportError:
        from voice_shared_runtime import config_fingerprint, SharedRuntimeError
    try:
        fingerprint = config_fingerprint(config)
    except SharedRuntimeError:
        return 'runtime_update_required'
    return _inspect_installation(config, fingerprint, epoch)


@lru_cache(maxsize=4)
def _inspect_installation(config, fingerprint=None, epoch=0):
    if not config.python.is_file() or not config.worker.is_file():
        return 'not_installed'
    try:
        config.wire()
        manifest = json.loads((config.model_dir/'scott-model.json').read_text(encoding='utf-8'))
        files = manifest['files']
        if not isinstance(files, list) or not files:
            return 'invalid_assets'
        required = {'config.json', 'generation_config.json', 'merges.txt', 'model.safetensors',
                    'preprocessor_config.json', 'tokenizer_config.json', 'vocab.json',
                    'speech_tokenizer/config.json', 'speech_tokenizer/configuration.json',
                    'speech_tokenizer/model.safetensors', 'speech_tokenizer/preprocessor_config.json'}
        if not required.issubset(files):
            return 'invalid_assets'
        for name in files:
            path = (config.model_dir/name).resolve()
            if not path.is_relative_to(config.model_dir.resolve()):
                return 'invalid_assets'
            if name in required and (not path.is_file() or not path.stat().st_size):
                return 'invalid_assets'
        recipe_id(config)  # Includes verification of the accepted reference SHA256.
        from hashlib import sha256
        for name in ('scott_voice_process.py', 'voice_shared_runtime.py', 'scott_voice_sdk.py'):
            copied_client = config.worker.parents[2]/'backend'/name
            if copied_client.is_file() and sha256(copied_client.read_bytes()).digest() != sha256(Path(__file__).with_name(name).read_bytes()).digest():
                return 'runtime_update_required'
    except (OSError, ValueError, KeyError, TypeError):
        return 'invalid_assets'
    return _probe_runtime(str(config.python), config.device, fingerprint)


inspect_installation.cache_clear = _inspect_installation.cache_clear
inspect_installation.cache_info = _inspect_installation.cache_info


def _track_request(method=None, *, preparation=False):
    def decorate(method):
        @wraps(method)
        def tracked(self,*args,**kwargs):
            listening = preparation and kwargs.get('for_listening') is True
            with self._lock:
                self._requests += 1
                self._listening_prepares += int(listening)
            try:
                return method(self,*args,**kwargs)
            finally:
                with self._lock:
                    self._requests -= 1
                    self._listening_prepares -= int(listening)
        return tracked
    return decorate(method) if method is not None else decorate


class ScottVoiceEngine:
    def __init__(self, config=None, factory=ScottVoiceProcess):
        self._application_defaults = config is None
        self.config = config or preferred_config()
        self.factory = factory
        self._lock = threading.RLock()
        self._client = None
        self._generation = 0
        self._state = 'idle'
        self._error = ''
        self._retry_at = 0
        self._requests = 0
        self._listening_prepares = 0
        self._listening_warmups = {}

    def describe(self):
        error = inspect_installation(self.config)
        with self._lock:
            return dict(available=not bool(error), experimental=True, local=True, engine='qwen',
                state='unavailable' if error else self._state,
                reason=MESSAGES.get(error, '') if error else MESSAGES.get(self._error, ''),
                error=error or self._error, device=self.config.device,
                acceleration_available=not bool(error) and self.config.device=='cuda',
                accelerated=self.config.rms_norm,
                streaming_available=not bool(error) and self.config.device=='cuda' and (self.config.worker.parent/'stream_voice.py').is_file())

    @property
    def generation(self):
        with self._lock:
            return self._generation

    @contextmanager
    def listening_preparation(self):
        token = object()
        with self._lock:
            generation = self._generation
            self._listening_warmups[token] = generation
        try:
            yield generation
        finally:
            with self._lock:
                self._listening_warmups.pop(token,None)

    def stream(self, text, profile, on_audio, on_abort=None, generation=None):
        return self.synthesize(text,profile,generation,on_audio=on_audio,on_abort=on_abort)

    def model_status(self):
        with self._lock:
            client = self._client
        return client.status() if client is not None and hasattr(client,'status') else dict(model_loaded=False,active=False)

    @_track_request(preparation=True)
    @measured('tts.prepare')
    def prepare(self, generation=None, *, for_listening=False):
        with self._lock:
            if generation is None:
                generation = self._generation
        error = inspect_installation(self.config)
        with self._lock:
            if generation != self._generation:
                raise VoiceProcessError('cancelled')
            if error:
                raise VoiceProcessError(error)
            if self._client is None:
                self._client = self.factory(self.config, timeout=60)
            client = self._client
            self._state, self._error = 'preparing', ''
        try:
            with phase('tts.worker_prepare'):
                result = client.prepare()
        except Exception as error:
            failure = error if isinstance(error,VoiceProcessError) else VoiceProcessError('synthesis_failed')
            with self._lock:
                if generation != self._generation:
                    raise VoiceProcessError('cancelled') from None
                self._state, self._error = 'idle', failure.code
            raise failure from None
        with self._lock:
            if generation != self._generation:
                raise VoiceProcessError('cancelled')
            self._state, self._error, self._retry_at = 'ready', '', 0
        return result

    @_track_request
    @measured('tts.synthesize')
    def synthesize(self, text, profile='natural', generation=None, *, on_audio=None, on_abort=None):
        with self._lock:
            if generation is None:
                generation = self._generation
        error = inspect_installation(self.config)
        with self._lock:
            if generation != self._generation:
                raise VoiceProcessError('cancelled')
            if error:
                raise VoiceProcessError(error)
            if time.monotonic() < self._retry_at:
                raise VoiceProcessError(self._error)
            if self._client is None:
                try:
                    self._client = self.factory(self.config, timeout=60)
                except (OSError, ValueError, TypeError):
                    self._state, self._error = 'error', 'synthesis_failed'
                    self._retry_at = time.monotonic()+30
                    raise VoiceProcessError('synthesis_failed') from None
            client = self._client
            self._state, self._error = 'preparing', ''
        try:
            if on_audio is not None:
                stream=getattr(client,'stream',None)
                if stream is None:
                    raise VoiceProcessError('stream_unavailable')
                with phase('tts.worker_stream'):
                    audio=stream(text,profile,on_audio,on_abort)
            else:
                with phase('tts.worker_synthesize'):
                    audio = client.synthesize(text, profile)
        except Exception as error:
            failure = error if isinstance(error, VoiceProcessError) else VoiceProcessError('synthesis_failed')
            with self._lock:
                if generation != self._generation:
                    raise VoiceProcessError('cancelled') from None
                if failure.code in ('cancelled', 'closed', 'stream_unavailable'):
                    self._state = 'idle'
                else:
                    self._state = 'error'
                    self._error = failure.code if failure.code in MESSAGES else 'synthesis_failed'
                    self._retry_at = time.monotonic()+30
            raise failure from None
        with self._lock:
            if generation != self._generation:
                raise VoiceProcessError('cancelled')
            self._state, self._error, self._retry_at = 'ready', '', 0
        return audio.path

    def cancel(self, generation=None, *, preserve_idle=False):
        # Detach before closing: a new request never reuses the cancelled worker.
        with self._lock:
            if generation is not None and generation!=self._generation:
                return
            listening = self._listening_prepares or self._generation in self._listening_warmups.values()
            if preserve_idle and listening and self._requests==self._listening_prepares:
                return  # A new command can use this same in-flight preparation.
            if preserve_idle and not self._requests and self._client is not None and \
                    self.model_status().get('model_loaded') and not self.model_status().get('active'):
                return
            self._generation += 1
            client, self._client = self._client, None
            self._state, self._error, self._retry_at = 'idle', '', 0
        if client is not None:
            client.close()

    close = cancel

    def set_acceleration(self, enabled):
        """Keep generation monotonic while changing workers and audio recipes."""
        if not isinstance(enabled,bool):
            raise ValueError('Expected acceleration boolean')
        with self._lock:
            self._generation+=1
            client,self._client=self._client,None
            accelerated=enabled and self.config.device=='cuda'
            threads=(_worker_cpu_threads(self.config.device,accelerated) if self._application_defaults
                     else self.config.cpu_threads)
            self.config=replace(self.config,rms_norm=accelerated,cpu_threads=threads)
            self._state,self._error,self._retry_at='idle','',0
        if client is not None:
            client.close()


_engine = None
_engine_lock = threading.Lock()


def get_engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = ScottVoiceEngine()
        return _engine


def cancel(*, preserve_idle=False):
    # Controls and shutdown must not construct or probe an unused engine.
    with _engine_lock:
        engine = _engine
    if engine is not None:
        engine.cancel(preserve_idle=preserve_idle) if preserve_idle else engine.cancel()


def reload_installation():
    """Switch runtimes without changing the chosen voice."""
    global _engine
    with _engine_lock:
        engine, _engine = _engine, None
        inspect_installation.cache_clear()
        _probe_runtime.cache_clear()
    if engine is not None:
        engine.close()


atexit.register(cancel)
