"""Optional local Scott Voice engine; models and Torch stay in the child process."""
from __future__ import annotations

import atexit
from dataclasses import replace
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
    from .scott_voice_process import ScottVoiceProcess, VoiceProcessConfig, VoiceProcessError, recipe_id, stop_process_tree
except ImportError:
    from scott_voice_process import ScottVoiceProcess, VoiceProcessConfig, VoiceProcessError, recipe_id, stop_process_tree

VOICE_ID = 'scott-voice'
ROOT = Path(__file__).resolve().parent.parent
PROFILES = {
    'natural': 'Исходный — уверенный и сдержанный',
    'restrained': 'Сдержанный — лёгкая цифровая окраска',
    'scott': 'Scott — умеренная цифровая окраска',
    'digital': 'Цифровой — выраженный машинный тембр',
}
MESSAGES = {
    'not_installed': 'Scott Voice не установлен. Доступен прежний голос.',
    'invalid_assets': 'Файлы Scott Voice неполные или повреждены.',
    'runtime_unavailable': 'Окружение Scott Voice недоступно.',
    'cuda_unavailable': 'Для Scott Voice не найден доступный CUDA GPU. CPU пока экспериментален.',
    'timeout': 'Scott Voice не успел подготовить звук. Используется резервный голос.',
    'synthesis_failed': 'Scott Voice не смог подготовить звук. Используется резервный голос.',
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


def config_at(root, cache_root=None):
    experiment = Path(root)/'experiments/voice_design'
    python = experiment/('.venv/Scripts/python.exe' if os.name == 'nt' else '.venv/bin/python')
    return VoiceProcessConfig(python=python, worker=experiment/'voice_worker.py',
        model_dir=experiment/'models/base',
        reference_json=Path(root)/'reports/voice-design/reference/reference.json',
        profiles_json=experiment/'robotic_profiles.json',
        cache_dir=Path(cache_root or root)/'audio_cache/scott-voice',
        device=os.getenv('SCOTT_VOICE_DEVICE', 'cuda').strip().lower())


def default_config(root=ROOT):
    # A separate optional installation takes priority once provisioning is complete.
    # Explicit overrides also report missing/incomplete installations in the catalog.
    override = os.getenv('SCOTT_VOICE_HOME', '').strip()
    home = Path(override).expanduser() if override else Path(root)/'voice-runtime'
    if override:
        return config_at(home, cache_root=root)
    try:
        marker = json.loads((home/'scott-install.json').read_text(encoding='utf-8'))
        ready = isinstance(marker, dict) and marker.get('ready') is True
    except (OSError, ValueError, TypeError):
        ready = False
    return config_at(home if ready else root, cache_root=root)


def preferred_config():
    """Application preferences stay separate from installer/benchmark defaults."""
    try:
        from .voice_config import get_scott_acceleration
    except ImportError:
        from voice_config import get_scott_acceleration
    config=default_config()
    return replace(config,rms_norm=get_scott_acceleration() and config.device=='cuda')


@lru_cache(maxsize=4)
def _probe_runtime(python, device):
    # Probe only in the optional interpreter; never load Qwen in the API process.
    script = ("import importlib.util,json; "
              "ready=all(importlib.util.find_spec(n) is not None for n in "
              "('torch','qwen_tts','soundfile','scipy')); "
              "import torch; print(json.dumps({'ready':ready,'cuda':torch.cuda.is_available()}))")
    env = dict(os.environ)
    for key in tuple(env):
        if key.upper().endswith(('_API_KEY', '_TOKEN')):
            env.pop(key, None)
    env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_IMPLICIT_TOKEN='1',
               PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
    try:
        process = subprocess.Popen([python, '-c', script], stdin=subprocess.DEVNULL,
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
        if device == 'cuda' and not info.get('cuda'):
            return 'cuda_unavailable'
        return ''
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 'runtime_unavailable'


@lru_cache(maxsize=4)
def inspect_installation(config):
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
        copied_client = config.worker.parents[2]/'backend/scott_voice_process.py'
        if copied_client.is_file():
            from hashlib import sha256
            if sha256(copied_client.read_bytes()).digest() != sha256(Path(__file__).with_name('scott_voice_process.py').read_bytes()).digest():
                return 'runtime_update_required'
    except (OSError, ValueError, KeyError, TypeError):
        return 'invalid_assets'
    return _probe_runtime(str(config.python), config.device)


def _track_request(method):
    @wraps(method)
    def tracked(self,*args,**kwargs):
        with self._lock:
            self._requests += 1
        try:
            return method(self,*args,**kwargs)
        finally:
            with self._lock:
                self._requests -= 1
    return tracked


class ScottVoiceEngine:
    def __init__(self, config=None, factory=ScottVoiceProcess):
        self.config = config or preferred_config()
        self.factory = factory
        self._lock = threading.RLock()
        self._client = None
        self._generation = 0
        self._state = 'idle'
        self._error = ''
        self._retry_at = 0
        self._requests = 0

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

    def stream(self, text, profile, on_audio, on_abort=None, generation=None):
        return self.synthesize(text,profile,generation,on_audio=on_audio,on_abort=on_abort)

    def model_status(self):
        with self._lock:
            client = self._client
        return client.status() if client is not None and hasattr(client,'status') else dict(model_loaded=False,active=False)

    @_track_request
    def prepare(self, generation=None):
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
                    self._state, self._error = 'fallback', 'synthesis_failed'
                    self._retry_at = time.monotonic()+30
                    raise VoiceProcessError('synthesis_failed') from None
            client = self._client
            self._state, self._error = 'preparing', ''
        try:
            if on_audio is not None:
                stream=getattr(client,'stream',None)
                if stream is None:
                    raise VoiceProcessError('stream_unavailable')
                audio=stream(text,profile,on_audio,on_abort)
            else:
                audio = client.synthesize(text, profile)
        except Exception as error:
            failure = error if isinstance(error, VoiceProcessError) else VoiceProcessError('synthesis_failed')
            with self._lock:
                if generation != self._generation:
                    raise VoiceProcessError('cancelled') from None
                if failure.code in ('cancelled', 'closed', 'stream_unavailable'):
                    self._state = 'idle'
                else:
                    self._state = 'fallback'
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
            self.config=replace(self.config,rms_norm=enabled and self.config.device=='cuda')
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
