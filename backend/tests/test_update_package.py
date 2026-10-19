"""Updater extraction checks with disposable packages and synthetic user files."""
import hashlib
import io
import json
import sys
import tarfile
import pytest
import update_package


@pytest.fixture
def installation(tmp_path):
    prefix=tmp_path/'Installed Scott AI';prefix.mkdir()
    (prefix/'.scott-linux-install.json').write_text('{}')
    (prefix/'.env').write_text('SYNTHETIC=preserve\n')
    (prefix/'history.json').write_text('{"synthetic":true}')
    return prefix


def bundle(tmp_path,extra=(),version='9.0.0'):
    root='ScottAI-9.0.0-Qt-linux-x86_64'
    archive=tmp_path/'update.tar.gz'
    files=[(root+'/VERSION.json',json.dumps(dict(version=version)).encode()),
           (root+'/launcher/ScottAIQt',b'fixture, never executed'),
           (root+'/install.sh',b'#!/bin/bash\nset -e\nprintf "applied" > "$2/applied"\n')]
    with tarfile.open(archive,'w:gz') as output:
        for name,data in files:
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;output.addfile(info,io.BytesIO(data))
        for info in extra:output.addfile(info,io.BytesIO(b'x'*info.size))
    return archive,hashlib.sha256(archive.read_bytes()).hexdigest()


@pytest.mark.skipif(sys.platform!='linux',reason='POSIX installer subprocess')
def test_verified_update_runs_installer_without_touching_synthetic_data(tmp_path,installation):
    archive,sha=bundle(tmp_path)
    update_package.apply(archive,sha,'9.0.0',installation)
    assert (installation/'applied').read_text()=='applied'
    assert (installation/'.env').read_text()=='SYNTHETIC=preserve\n'
    assert (installation/'history.json').read_text()=='{"synthetic":true}'
    assert not list(tmp_path.glob('release-*'))


@pytest.mark.parametrize('name',['../escape','/absolute','ScottAI-9.0.0-Qt-linux-x86_64/../../escape',
    'ScottAI-9.0.0-Qt-linux-x86_64/.env','ScottAI-9.0.0-Qt-linux-x86_64/backend/data/chat.json',
    'AnotherRoot/file'])
def test_unsafe_archives_are_rejected_before_installer(tmp_path,installation,name):
    info=tarfile.TarInfo(name);info.size=1
    archive,sha=bundle(tmp_path,[info])
    with pytest.raises((ValueError,tarfile.TarError)):update_package.apply(archive,sha,'9.0.0',installation)
    assert not (installation/'applied').exists()
    assert (installation/'history.json').read_text()=='{"synthetic":true}'


def test_corrupt_download_cannot_run_installer(tmp_path,installation):
    archive,sha=bundle(tmp_path);archive.write_bytes(archive.read_bytes()+b'corruption')
    with pytest.raises(ValueError,match='сумма'):update_package.apply(archive,sha,'9.0.0',installation)
    assert not (installation/'applied').exists()


def test_writable_appimage_payload_never_runs_tar_installer(tmp_path,installation):
    (installation/'.scott-linux-install.json').write_text('{"image_layout":1}')
    archive,sha=bundle(tmp_path)
    with pytest.raises(ValueError,match='AppImage'):
        update_package.apply(archive,sha,'9.0.0',installation)
    assert not (installation/'applied').exists()
    assert (installation/'history.json').read_text()=='{"synthetic":true}'


def test_wrong_version_is_rejected(tmp_path,installation):
    archive,sha=bundle(tmp_path,version='8.0.0')
    with pytest.raises(ValueError,match='Версия'):update_package.apply(archive,sha,'9.0.0',installation)
    assert not (installation/'applied').exists()


def test_external_link_cannot_escape_extraction(tmp_path,installation):
    info=tarfile.TarInfo('ScottAI-9.0.0-Qt-linux-x86_64/external');info.type=tarfile.SYMTYPE;info.linkname=str(tmp_path/'outside')
    archive,sha=bundle(tmp_path,[info])
    with pytest.raises((ValueError,tarfile.TarError)):update_package.apply(archive,sha,'9.0.0',installation)
    assert not (installation/'applied').exists()
