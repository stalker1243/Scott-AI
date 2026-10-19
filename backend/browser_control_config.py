"""Optional browser runtime; no browser or third-party imports in the API process."""
import json
import os
from pathlib import Path
import shutil
import threading
import time

VERSION = '1.63.0'
try:
    from .storage_paths import backend_path
except ImportError:
    from storage_paths import backend_path

HOME = backend_path('browser-control')
ACTIONS = {'install', 'home', 'search', 'play', 'select', 'pause', 'resume', 'close'}
ACTIVE = {'running', 'cancelling'}


def installed(home=HOME):
    try:
        marker = json.loads((Path(home) / 'ready.json').read_text(encoding='utf-8'))
        return marker.get('version') == VERSION and (Path(home) / 'libraries/playwright/__init__.py').is_file()
    except (OSError, ValueError, AttributeError):
        return False


def browser_options(home=HOME):
    if os.name == 'nt':
        for channel, suffix in [('msedge', 'Microsoft/Edge/Application/msedge.exe'),
                                ('chrome', 'Google/Chrome/Application/chrome.exe')]:
            for folder in ('PROGRAMFILES(X86)', 'PROGRAMFILES', 'LOCALAPPDATA'):
                base = os.environ.get(folder)
                if base and (Path(base) / suffix).is_file():
                    return {'channel': channel}
    else:
        for name in ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'microsoft-edge'):
            path = shutil.which(name)
            if path:
                return {'executable_path': path}
    return {} # Playwright's optional Chromium, in our own browser cache.


def clean_environment(home):
    env = {key: value for key, value in os.environ.items()
           if not key.upper().endswith(('_API_KEY', '_TOKEN'))
           and key.upper() not in {'PYTHONPATH', 'PYTHONHOME', 'OPENAI_API_KEY', 'AWS_SECRET_ACCESS_KEY',
                                   'AWS_ACCESS_KEY_ID', 'SCOTT_VOICE_HOME'}}
    env.update(PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8',
               PLAYWRIGHT_BROWSERS_PATH=str(Path(home) / 'browsers'))
    return env


def watch_owner(pid, created):
    if not pid:
        return
    def watch():
        import psutil
        while True:
            time.sleep(.5)
            try:
                if abs(psutil.Process(pid).create_time() - created) < .01:
                    continue
            except psutil.Error:
                pass
            # Only this installer/worker's descendants are stopped. A cached
            # owner PID by itself is never enough to identify the parent.
            try:
                for child in reversed(psutil.Process().children(recursive=True)):
                    try:
                        child.kill()
                    except psutil.Error:
                        pass
            finally:
                os._exit(0)
    threading.Thread(target=watch, daemon=True).start()
