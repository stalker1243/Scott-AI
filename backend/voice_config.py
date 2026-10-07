"""Persist an explicit voice choice without changing environment defaults."""

import json
import threading
from pathlib import Path

try:
    from .storage import atomic_write_text
    from .speech_buffer import BUFFER_MODES
except ImportError:
    from storage import atomic_write_text
    from speech_buffer import BUFFER_MODES

CONFIG_PATH = Path(__file__).resolve().parent / "data" / "voice_config.json"
_lock = threading.RLock()


def get_voice(default: str, allowed) -> str:
    with _lock:
        try:
            settings = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            voice = settings.get("voice") if isinstance(settings, dict) else None
            if isinstance(voice, str) and voice in allowed:
                return voice
        except (OSError, ValueError):
            pass
    return default


def _read() -> dict:
    try:
        value = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def get_scott_profile() -> str:
    with _lock:
        value = _read().get('scott_profile', 'natural')
    return value if value in ('natural', 'restrained', 'scott', 'digital') else 'natural'


def get_scott_streaming() -> bool:
    with _lock:
        return _read().get('scott_streaming') is True


def get_scott_acceleration() -> bool:
    with _lock:
        return _read().get('scott_acceleration') is True


def get_scott_buffer() -> str:
    with _lock:
        value = _read().get('scott_buffer', 'immediate')
    return value if isinstance(value, str) and value in BUFFER_MODES else 'immediate'


def get_fallback_voice(default: str, allowed) -> str:
    with _lock:
        value = _read().get('fallback_voice')
    return value if isinstance(value, str) and value in allowed and value != 'scott-voice' else default


def save_voice(voice: str, profile=None, streaming=None, acceleration=None, buffer_mode=None) -> None:
    if streaming is not None and (voice!='scott-voice' or not isinstance(streaming,bool)):
        raise ValueError('Invalid Scott Voice streaming choice')
    if acceleration is not None and (voice!='scott-voice' or not isinstance(acceleration,bool)):
        raise ValueError('Invalid Scott Voice acceleration choice')
    if buffer_mode is not None and (voice != 'scott-voice' or not isinstance(buffer_mode, str) or buffer_mode not in BUFFER_MODES):
        raise ValueError('Invalid Scott Voice buffer choice')
    with _lock:
        settings = _read()
        if voice == 'scott-voice' and settings.get('voice') not in (None, 'scott-voice'):
            settings['fallback_voice'] = settings['voice']
        settings['voice'] = voice
        if profile is not None:
            if profile not in ('natural', 'restrained', 'scott', 'digital'):
                raise ValueError('Unknown Scott Voice profile')
            settings['scott_profile'] = profile
        if streaming is not None:
            settings['scott_streaming'] = streaming
        if acceleration is not None:
            settings['scott_acceleration'] = acceleration
        if buffer_mode is not None:
            settings['scott_buffer'] = buffer_mode
        atomic_write_text(CONFIG_PATH, json.dumps(settings, ensure_ascii=False, indent=2))
