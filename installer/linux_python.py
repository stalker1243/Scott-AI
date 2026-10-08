"""Pinned, relocatable CPython for the Linux distribution (no system install)."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import posixpath
import shutil
import tarfile
import tempfile
import urllib.request
from urllib.parse import quote

VERSION = '3.13.16'
RELEASE = '20261003'
NAME = f'cpython-{VERSION}+{RELEASE}-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz'
URL = f'https://github.com/astral-sh/python-build-standalone/releases/download/{RELEASE}/{quote(NAME)}'
SHA256 = '4595c5589fff7bf0cb158d9a88a797e0d791fa33830770fcb7bf3f4b104feeae'
CORE = ('bin/python3.13', 'lib/python3.13/os.py', 'lib/python3.13/venv/__init__.py')
RECEIPT = '.scott-python.json'
ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(cache):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache/NAME
    if archive.is_file() and digest(archive) == SHA256:
        return archive
    temporary = cache/(NAME+'.part')
    try:
        with urllib.request.urlopen(URL, timeout=30) as source, temporary.open('wb') as target:
            while block := source.read(1024*1024):
                target.write(block)
        if digest(temporary) != SHA256:
            raise ValueError('CPython archive checksum does not match the pinned release.')
        os.replace(temporary, archive)
    finally:
        temporary.unlink(missing_ok=True)
    return archive


def copy_python(output, archive=None):
    output = Path(output).resolve()
    target = output/'python-runtime'
    if target.exists() or target.is_symlink():
        raise ValueError('Python output already exists.')
    archive = Path(archive) if archive else download(ROOT/'installer/.cache/linux-python')
    if digest(archive) != SHA256:
        raise ValueError('CPython archive checksum does not match the pinned release.')
    with tempfile.TemporaryDirectory(prefix='.python-extract-', dir=output) as temporary:
        with tarfile.open(archive) as tar:
            members = tar.getmembers()
            for member in members:
                path = PurePosixPath(member.name)
                if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != 'python':
                    raise ValueError('CPython archive contains an invalid path.')
                if not (member.isfile() or member.isdir() or member.issym()):
                    raise ValueError('CPython archive contains an unsupported entry.')
                if member.mode & 0o7000:
                    raise ValueError('CPython archive contains privileged permissions.')
                if member.issym():
                    resolved = posixpath.normpath(str(path.parent/PurePosixPath(member.linkname)))
                    if PurePosixPath(member.linkname).is_absolute() or not resolved.startswith('python/'):
                        raise ValueError('CPython archive contains an external link.')
            tar.extractall(temporary, members=members, filter='data')
        base = Path(temporary)/'python'
        if not all((base/name).is_file() for name in CORE):
            raise ValueError('CPython archive is incomplete.')
        core = {name: digest(base/name) for name in CORE}
        receipt = {'version': VERSION, 'release': RELEASE, 'sha256': SHA256,
                   'source': URL, 'core': core}
        (base/RECEIPT).write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        shutil.move(str(base), str(target))
    return target
