"""Verify the runtime archive before allowing it into a distribution."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('linux_python_builder', ROOT/'installer/linux_python.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def archive(tmp_path, entries):
    path = tmp_path/'synthetic-python.tar.gz'
    with tarfile.open(path, 'w:gz') as tar:
        for name, payload in entries:
            member = tarfile.TarInfo(name)
            if isinstance(payload, tuple):
                member.type = tarfile.SYMTYPE
                member.linkname = payload[0]
                tar.addfile(member)
            else:
                member.size = len(payload)
                tar.addfile(member, io.BytesIO(payload))
    return path


def test_rejects_checksum_before_extract(tmp_path):
    path = archive(tmp_path, [('python/bin/python3.13', b'synthetic')])
    with pytest.raises(ValueError, match='checksum'):
        builder.copy_python(tmp_path, path)
    assert not (tmp_path/'python-runtime').exists()


@pytest.mark.parametrize('entry', ['../outside', '/outside', 'other/bin/python'])
def test_rejects_archive_paths(tmp_path, entry, monkeypatch):
    path = archive(tmp_path, [(entry, b'synthetic')])
    monkeypatch.setattr(builder, 'SHA256', builder.digest(path))
    with pytest.raises(ValueError, match='path'):
        builder.copy_python(tmp_path, path)
    assert not (tmp_path/'python-runtime').exists()


@pytest.mark.parametrize('link', ['/outside', '../../../outside', '../../outside'])
def test_rejects_external_links(tmp_path, link, monkeypatch):
    path = archive(tmp_path, [('python/bin/python3', (link,))])
    monkeypatch.setattr(builder, 'SHA256', builder.digest(path))
    with pytest.raises((ValueError, tarfile.FilterError)):
        builder.copy_python(tmp_path, path)
    assert not (tmp_path/'python-runtime').exists()


def test_creates_receipt_for_exact_core(tmp_path, monkeypatch):
    path = archive(tmp_path, [('python/'+name, b'synthetic '+name.encode()) for name in builder.CORE])
    monkeypatch.setattr(builder, 'SHA256', builder.digest(path))
    target = builder.copy_python(tmp_path, path)
    import json
    receipt = json.loads((target/builder.RECEIPT).read_text())
    assert receipt['sha256'] == builder.digest(path)
    assert set(receipt['core']) == set(builder.CORE)
    assert all(hashlib.sha256((target/name).read_bytes()).hexdigest() == sha
               for name, sha in receipt['core'].items())
    with pytest.raises(ValueError, match='already exists'):
        builder.copy_python(tmp_path, path)


def test_upstream_bytecode_is_not_published_with_the_runtime(tmp_path,monkeypatch):
    entries=[('python/'+name,b'synthetic '+name.encode()) for name in builder.CORE]
    entries += [('python/lib/python3.13/encodings/__init__.py',b'# source stays'),
        ('python/lib/python3.13/encodings/__pycache__/__init__.cpython-313.pyc',b'upstream cache'),
        ('python/lib/python3.13/other.pyc',b'upstream bytecode'),
        ('python/lib/python3.13/other.pyo',b'upstream optimized bytecode')]
    path=archive(tmp_path,entries);monkeypatch.setattr(builder,'SHA256',builder.digest(path))
    target=builder.copy_python(tmp_path,path)
    assert (target/'lib/python3.13/encodings/__init__.py').read_bytes()==b'# source stays'
    assert not any('__pycache__' in path.parts or path.suffix in ('.pyc','.pyo') for path in target.rglob('*'))
    assert all((target/name).is_file() for name in builder.CORE)
