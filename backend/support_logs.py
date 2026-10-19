"""Bounded technical logs shared by setup, voice provisioning and support export."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import threading
try:
    from .platform_paths import xdg_home, private_directory
except ImportError:
    from platform_paths import xdg_home, private_directory

ROOT = Path(__file__).resolve().parent.parent
LIMIT = 2 * 1024 * 1024
_lock = threading.RLock()


def log_directory():
    override = os.getenv('SCOTT_LOG_DIR', '').strip()
    if override:
        return Path(override).expanduser()
    if os.name == 'nt':
        return Path(os.getenv('LOCALAPPDATA') or Path.home()/'AppData/Local')/'ScottAI/logs'
    return xdg_home('XDG_STATE_HOME')/'ScottAI/logs'


def backend_log_directory():
    return ROOT/'backend/logs' if os.name == 'nt' else log_directory()


def backend_error_path():
    return ROOT/'backend_errors.log' if os.name == 'nt' else log_directory()/'backend_errors.log'


def report_directory():
    return ROOT/'reports' if os.name == 'nt' else xdg_home('XDG_STATE_HOME')/'ScottAI/reports'


def _secret_name(name):
    return any(word in name.upper() for word in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD', 'AUTHORIZATION'))


def secret_values(root=ROOT):
    values = {value for name, value in os.environ.items() if _secret_name(name) and value}
    root = Path(root).resolve()
    # Read only credential fields to remove opaque saved tokens from old logs.
    # These files themselves are never included in a support report.
    try:
        from .storage_paths import layout_for
    except ImportError:
        from storage_paths import layout_for
    layout = layout_for(root)
    # Inspect paths without triggering migration during offline diagnostics.
    candidates = [(root/'.env', root), (root/'backend/data/ai_config.json', root)]
    if layout.external:
        candidates.extend(((layout.environment, layout.config),
                           (layout.backend('ai_config.json'), layout.config)))
    for path, boundary in candidates:
        try:
            if any(part.is_symlink() for part in (path, *path.parents)) or not path.resolve().is_relative_to(boundary) or path.stat().st_size > 1024*1024:
                continue
            text = path.read_text(encoding='utf-8-sig')
            if path.name == '.env':
                for line in text.splitlines():
                    name, separator, value = line.removeprefix('export ').partition('=')
                    if separator and _secret_name(name.strip()):
                        value = value.strip().strip('\"\'')
                        if value:
                            values.add(value)
            else:
                def visit(item, sensitive=False):
                    if isinstance(item, dict):
                        for name, value in item.items():
                            visit(value, sensitive or _secret_name(name))
                    elif isinstance(item, list):
                        for child in item:
                            visit(child, sensitive)
                    elif sensitive and isinstance(item, str) and item:
                        values.add(item)
                visit(json.loads(text))
        except (OSError, ValueError):
            continue
    return values


PATTERNS = (
    re.compile(r'(?:sk-|gsk_|github_pat_|gh[pousr]_)[A-Za-z0-9_-]{8,}'),
    re.compile(r'AIza[A-Za-z0-9_-]{12,}'),
    re.compile(r'Bearer\s+[^\s\"\'<>]+', re.I),
    re.compile(r'/bot\d+:[A-Za-z0-9_-]+'),
    re.compile(r'(?i)((?:[\w-]*(?:api[_-]?key|token|secret|password)|authorization|токен|ключ)\s*[\"\']?\s*[:=]\s*)[\"\']?[^\s,;\"\']+'),
    re.compile(r'(?i)(https?://)[^\s/@:]+:[^\s/@]+@'),
)
PRIVATE_LINE = re.compile(r'(?i)(?:user[_ ]?(?:text|message|prompt)|assistant[_ ](?:text|message)|recognized[_ ]text|распознано|распознал|текст команды|user command|prompt\s*[:=]|пользователь\s*\([^)]*\)\s*:|🤖\s*Scott\s*:|ответ от ИИ\s*:|ищу в браузере\s*:|команда\s*:|озвучено\s*:|перебили\s*:|своё эхо|🔇\s*Мимо|напоминание\s*:|выполняю отложенное\s*:)\s*[:=]?')


def redact(text, root=ROOT):
    text = str(text)
    for value in sorted(secret_values(root), key=len, reverse=True):
        if len(value) >= 4:
            text = text.replace(value, '***СКРЫТО***')
        else:
            text = re.sub(r'(?<!\w)'+re.escape(value)+r'(?!\w)', '***СКРЫТО***', text)
    for pattern in PATTERNS:
        text = pattern.sub('***СКРЫТО***', text)
    text = '\n'.join('[Текст запроса скрыт]' if PRIVATE_LINE.search(line) else line for line in text.split('\n'))
    for path, label in ((Path(root), '<APP>'), (Path.home(), '<HOME>')):
        for form in {str(path), str(path).replace('\\', '/')}:
            if len(form) > 3:
                text = text.replace(form, label)
    return text


def append_log(name, message, root=ROOT):
    if not re.fullmatch(r'[a-z][a-z0-9-]*\.log', name):
        raise ValueError('Unknown technical log name')
    try:
        from datetime import datetime
        line = (datetime.now().isoformat(timespec='seconds')+' '+redact(message, root)+'\n').encode('utf-8')[-LIMIT:]
        with _lock:
            folder = log_directory()
            private_directory(folder)
            target = folder/name
            if target.is_symlink():
                return
            if target.exists() and target.stat().st_size + len(line) > LIMIT:
                for index in (2, 1):
                    source = folder/(name+('.1' if index == 2 else ''))
                    destination = folder/(name+f'.{index}')
                    if source.is_file() and not source.is_symlink() and not destination.is_symlink():
                        os.replace(source, destination)
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(line)
    except OSError:
        pass  # A failed log write must not prevent setup or startup.
