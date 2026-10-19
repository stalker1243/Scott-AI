"""Small stdlib path helpers shared by Linux setup and offline diagnostics."""
import os
from pathlib import Path

XDG_DEFAULTS = {'XDG_DATA_HOME': '.local/share', 'XDG_CONFIG_HOME': '.config',
                'XDG_STATE_HOME': '.local/state', 'XDG_CACHE_HOME': '.cache'}


def xdg_home(variable, *, env=None, home=None):
    """The XDG specification requires absolute paths; ignore relative values."""
    env = os.environ if env is None else env
    value = env.get(variable, '')
    if value and Path(value).is_absolute():
        return Path(value)
    return Path(home if home is not None else Path.home()) / XDG_DEFAULTS[variable]


def private_directory(path):
    """Create missing directories as 0700 without changing existing permissions."""
    path = Path(path)
    missing, current = [], path
    while not current.exists():
        missing.append(current)
        if current == current.parent:
            break
        current = current.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700, exist_ok=True)
    return path
