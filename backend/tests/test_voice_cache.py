"""Eviction owns only complete Scott Voice pairs and protects recent playback."""
import json
import os
from pathlib import Path

import pytest

from voice_cache import prune, touch

pytestmark = pytest.mark.unit


def pair(directory, number, accessed, size=100):
    key = f'{number:064x}'
    path = directory/f'scott-voice-{key}.wav'
    path.write_bytes(b'x'*size)
    metadata = path.with_suffix('.json')
    metadata.write_text(json.dumps(dict(protocol=1, key=key, sha256='test')), encoding='utf-8')
    os.utime(metadata, (accessed, accessed))
    return path


def test_lru_bounds_count_and_bytes(tmp_path):
    old = pair(tmp_path, 1, 100)
    middle = pair(tmp_path, 2, 200)
    newest = pair(tmp_path, 3, 300)
    result = prune(tmp_path, max_bytes=100000, max_entries=2, now=1000)
    assert result['removed'] == 1 and not old.exists() and not old.with_suffix('.json').exists()
    assert middle.exists() and newest.exists() and not result['over_budget']
    result = prune(tmp_path, max_bytes=newest.stat().st_size+newest.with_suffix('.json').stat().st_size, max_entries=2, now=1000)
    assert result['removed'] == 1 and not middle.exists() and newest.exists()


def test_recent_and_current_audio_survive_a_full_cache(tmp_path):
    active = pair(tmp_path, 1, 900)
    protected = pair(tmp_path, 2, 100)
    stale = pair(tmp_path, 3, 200)
    result = prune(tmp_path, max_entries=1, protected=[protected], now=1000)
    assert active.exists() and protected.exists() and not stale.exists()
    assert result['over_budget']  # Temporary grace can exceed the budget.
    result = prune(tmp_path, max_entries=1, protected=[protected], now=1201)
    assert not active.exists() and protected.exists() and not result['over_budget']


def test_cache_hits_update_lru_without_changing_metadata(tmp_path):
    path = pair(tmp_path, 1, 100)
    before = path.with_suffix('.json').read_bytes()
    touch(path)
    assert path.with_suffix('.json').stat().st_mtime > 100
    assert path.with_suffix('.json').read_bytes() == before


def test_unrelated_or_incomplete_data_is_never_removed(tmp_path):
    pair(tmp_path, 1, 100)
    protected = [tmp_path/'personal.wav', tmp_path/'.pending-test.wav', tmp_path/'scott-voice-not-a-key.wav']
    for path in protected:
        path.write_bytes(b'preserved')
    orphan = tmp_path/('scott-voice-'+('f'*64)+'.wav')
    orphan.write_bytes(b'orphan')
    protected.append(orphan)
    invalid = pair(tmp_path, 2, 100)
    invalid.with_suffix('.json').write_text('{broken', encoding='utf-8')
    protected.extend([invalid, invalid.with_suffix('.json')])
    before = {path: path.read_bytes() for path in protected}
    prune(tmp_path, max_bytes=1, now=1000)
    assert all(path.read_bytes() == content for path, content in before.items())


def test_locked_audio_is_retained_for_next_pass(tmp_path, monkeypatch):
    path = pair(tmp_path, 1, 100)
    original = Path.unlink
    def locked(self, *args, **kwargs):
        if self == path:
            raise PermissionError('playing')
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', locked)
    result = prune(tmp_path, max_bytes=1, now=1000)
    assert path.exists() and path.with_suffix('.json').exists() and result['over_budget']


@pytest.mark.parametrize('limits', [{'max_bytes':0}, {'max_entries':-1}, {'max_bytes':True}, {'max_entries':'100'}])
def test_invalid_limits_never_delete(tmp_path, limits):
    path = pair(tmp_path, 1, 100)
    with pytest.raises(ValueError):
        prune(tmp_path, **limits)
    assert path.exists()
