"""Small, local visual notifications. No application names or user messages."""
import configparser
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import uuid

try:
    from .platform_paths import xdg_home
except ImportError:
    from platform_paths import xdg_home


def state_directory():
    """Match Qt's GenericConfigLocation; an override also isolates test runs."""
    override = os.environ.get('SCOTT_PET_STATE_DIR')
    if override:
        path = Path(override)
        return path if path.is_absolute() else None
    if sys.platform == 'win32':
        base = os.environ.get('LOCALAPPDATA')
        if not base or not Path(base).is_absolute():
            return None
        base = Path(base)
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library/Preferences'
    else:
        base = xdg_home('XDG_CONFIG_HOME')
    return base / 'ScottAI/desktop-pet'


def application_opened():
    """Best effort after a successful launch; never affects the command result.

    Only an existing enabled companion receives notifications. The one-slot
    mailbox coalesces rapid launches and is replaced atomically. No backend
    connection, process enumeration, model or extra dependency is required.
    """
    temporary = None
    try:
        root = state_directory()
        if root is None or root.is_symlink() or not root.is_dir():
            return False
        settings = root / 'settings.ini'
        if settings.is_symlink() or not settings.is_file() or settings.stat().st_size > 16384:
            return False
        config = configparser.ConfigParser(interpolation=None)
        config.read_string(settings.read_text(encoding='utf-8-sig'))
        if config.get('General', 'enabled', fallback='false').strip().lower() != 'true':
            return False
        target = root / 'activity.json'
        if target.is_symlink() or (target.exists() and not target.is_file()):
            return False
        payload = dict(version=1, event='application_opened', id=uuid.uuid4().hex,
                       created_ms=time.time_ns() // 1_000_000)
        descriptor, temporary = tempfile.mkstemp(prefix='.activity-', suffix='.tmp', dir=root)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(payload, stream, separators=(',', ':'))
        os.replace(temporary, target)
        temporary = None
        return True
    except (OSError, ValueError, UnicodeError, configparser.Error):
        return False
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass
