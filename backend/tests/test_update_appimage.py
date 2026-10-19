"""AppImage replacement: synthetic bytes; no network, models or live files."""
import hashlib
import os
from pathlib import Path
import stat
import sys
import pytest
import update_appimage as updater

pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Linux inode/dirfd/flock')


def image_bytes(label):
    head = bytearray(64)
    head[:6] = b'\x7fELF\x02\x01'
    head[8:11] = b'AI\x02'
    head[18:20] = b'\x3e\x00'
    return bytes(head)+label


@pytest.fixture
def images(tmp_path, monkeypatch):
    target = tmp_path/'Scott AI Юникод.AppImage'
    target.write_bytes(image_bytes(b'old'))
    target.chmod(0o750)
    archive = tmp_path/'download.AppImage'
    archive.write_bytes(image_bytes(b'new'))
    monkeypatch.setattr(updater, 'metadata', lambda *a: ({'version': '9.0.0'}, {'image_layout': 1}))
    return target, archive, updater.snapshot(target), hashlib.sha256(archive.read_bytes()).hexdigest()


def test_atomic_replacement_keeps_previous_image_and_permissions(images):
    target, archive, expected, sha = images
    old = target.read_bytes()
    result = updater.apply(archive, sha, '9.0.0', expected)
    assert target.read_bytes() == archive.read_bytes()
    assert Path(result['backup']).read_bytes() == old
    assert stat.S_IMODE(target.stat().st_mode) == 0o750
    assert target.stat().st_nlink == 1 and Path(result['backup']).stat().st_nlink == 1
    assert not list(target.parent.glob('.scott-update-*'))


@pytest.mark.parametrize('problem', ['hash', 'version', 'format', 'header', 'identity'])
def test_failed_validation_preserves_original(images, monkeypatch, problem):
    target, archive, expected, sha = images
    before = target.read_bytes()
    if problem == 'hash': sha = '0'*64
    if problem == 'version': monkeypatch.setattr(updater, 'metadata', lambda *a: ({'version': '8.0.0'}, {'image_layout': 1}))
    if problem == 'format': monkeypatch.setattr(updater, 'metadata', lambda *a: ({'version': '9.0.0'}, {}))
    if problem == 'header':
        archive.write_bytes(b'not an AppImage'*10);sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    if problem == 'identity': expected['inode'] = '0'
    with pytest.raises(ValueError): updater.apply(archive, sha, '9.0.0', expected)
    assert target.read_bytes() == before
    assert not list(target.parent.glob('.scott-update-*'))
    assert not list(target.parent.glob('.scott-previous-*'))


def test_manual_replacement_during_validation_is_preserved(images, monkeypatch):
    target, archive, expected, sha = images
    manual = target.parent/'manual-image'
    manual.write_bytes(image_bytes(b'manual'))
    def inspect(*args):
        os.replace(manual, target)
        return {'version': '9.0.0'}, {'image_layout': 1}
    monkeypatch.setattr(updater, 'metadata', inspect)
    with pytest.raises(ValueError, match='изменился'):
        updater.apply(archive, sha, '9.0.0', expected)
    assert target.read_bytes() == image_bytes(b'manual')
    assert not list(target.parent.glob('.scott-previous-*'))


def test_failed_commit_removes_only_its_own_staging_and_backup(images, monkeypatch):
    target, archive, expected, sha = images
    unknown = target.parent/'.scott-previous-unknown.AppImage'
    unknown.write_bytes(b'preserve')
    def fail(*a, **kw): raise OSError('synthetic rename failure')
    monkeypatch.setattr(updater.os, 'replace', fail)
    with pytest.raises(OSError): updater.apply(archive, sha, '9.0.0', expected)
    assert updater.snapshot(target) == expected
    assert unknown.read_bytes() == b'preserve'
    assert list(target.parent.glob('.scott-previous-*')) == [unknown]
    assert not list(target.parent.glob('.scott-update-*'))


def test_insufficient_space_stops_before_creating_staging(images, monkeypatch):
    target, archive, expected, sha = images
    monkeypatch.setattr(updater.shutil, 'disk_usage', lambda *a: type('Disk', (), {'free': 0})())
    with pytest.raises(ValueError, match='места'):
        updater.apply(archive, sha, '9.0.0', expected)
    assert updater.snapshot(target) == expected
    assert not list(target.parent.glob('.scott-*'))


def test_aliases_and_linked_parent_cannot_select_target(images):
    target, archive, expected, sha = images
    link = target.parent/'linked'
    link.symlink_to(target.parent, target_is_directory=True)
    with pytest.raises(ValueError, match='ссылку'): updater.snapshot(link/target.name)
    alias = target.parent/'hardlink'
    os.link(target, alias)
    with pytest.raises(ValueError): updater.snapshot(target)
    assert target.read_bytes() == image_bytes(b'old')


def test_directory_sync_failure_reports_committed_image(images, monkeypatch):
    target, archive, expected, sha = images
    real = updater.os.fsync
    def sync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode): raise OSError('synthetic directory sync failure')
        return real(fd)
    monkeypatch.setattr(updater.os, 'fsync', sync)
    result = updater.apply(archive, sha, '9.0.0', expected)
    assert result['updated'] and result['warning']
    assert target.read_bytes() == archive.read_bytes() and Path(result['backup']).exists()
