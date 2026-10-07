"""Bound only complete Scott Voice cache pairs; never traverse or delete other data."""
from pathlib import Path
import json
import os
import re
import time

_NAME = re.compile(r'scott-voice-([0-9a-f]{64})\.wav\Z')


def _link(path):
    return path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction())


def touch(path):
    try:
        path = Path(path)
        if not _link(path) and not _link(path.with_suffix('.json')):
            os.utime(path.with_suffix('.json'), None)
    except OSError:
        pass


def prune(directory, max_bytes=512*1024*1024, max_entries=1000, protected=(), min_age=120, now=None):
    """LRU budget with a two-minute grace for queued/playing audio and current output."""
    if (isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1 or
            isinstance(max_entries, bool) or not isinstance(max_entries, int) or max_entries < 1):
        raise ValueError('Invalid voice cache budget')
    directory = Path(directory)
    summary = dict(entries=0, bytes=0, removed=0, over_budget=False)
    if not directory.is_dir() or _link(directory):
        return summary
    now = time.time() if now is None else now
    protected = {Path(path).resolve() for path in protected}
    pairs = []
    try:
        for audio in directory.iterdir():
            match = _NAME.fullmatch(audio.name)
            if not match or _link(audio) or not audio.is_file():
                continue
            metadata = audio.with_suffix('.json')
            if _link(metadata) or not metadata.is_file():
                continue
            try:
                info = json.loads(metadata.read_text(encoding='utf-8'))
                if not isinstance(info, dict) or info.get('protocol') != 1 or info.get('key') != match[1]:
                    continue
                stat = metadata.stat()
                size = audio.stat().st_size+stat.st_size
                pairs.append((stat.st_mtime, audio, metadata, size))
            except (OSError, ValueError):
                continue
    except OSError:
        return summary
    summary.update(entries=len(pairs), bytes=sum(pair[3] for pair in pairs))
    for accessed, audio, metadata, size in sorted(pairs):
        if summary['bytes'] <= max_bytes and summary['entries'] <= max_entries:
            break
        if audio.resolve() in protected or now-accessed < min_age:
            continue
        try:
            if _link(audio) or _link(metadata):
                continue
            audio.unlink()
            metadata.unlink(missing_ok=True)
        except OSError:
            continue  # Open audio may be locked by a Windows player; retry next time.
        summary['removed'] += 1
        summary['entries'] -= 1
        summary['bytes'] -= size
    summary['over_budget'] = summary['bytes'] > max_bytes or summary['entries'] > max_entries
    return summary
