"""Stable, private Python for Linux packages, including changing read-only mounts.

Only stdlib is used: this runs before backend dependencies are installed. Existing
environments are never relocated or deleted. Slots are keyed by the bundled Python
archive hash, so replacing an application does not replace a running Python base.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

try:
    from .platform_paths import private_directory, xdg_home
except ImportError:
    # -I intentionally omits the script directory; load only our sibling helper.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from platform_paths import private_directory, xdg_home

CORE = frozenset(('bin/python3.13', 'lib/python3.13/os.py', 'lib/python3.13/venv/__init__.py'))
OWNER = '.scott-runtime.json'


def no_links(path):
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError('Путь Python содержит символическую ссылку. Исходные файлы сохранены.')


def read_receipt(base):
    base = Path(base)
    value = json.loads((base/'.scott-python.json').read_text(encoding='utf-8'))
    if not isinstance(value, dict) or not isinstance(value.get('core'), dict):
        raise ValueError('Некорректный перечень файлов Python.')
    sha = value.get('sha256', '')
    if (not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha)
            or not str(value.get('version', '')).startswith('3.13.') or set(value.get('core', {})) != CORE):
        raise ValueError('В пакете отсутствует проверенный Python 3.13.')
    for name, expected in value['core'].items():
        file = base/name
        if not file.resolve().is_relative_to(base.resolve()):
            raise ValueError('Файлы Python находятся за пределами пакета.')
        with file.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                raise ValueError('Файлы встроенного Python повреждены.')
    return value


def write_json(path, value):
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                    prefix='.runtime-', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def locked(path, timeout=60):
    import fcntl
    no_links(path)
    with path.open('a+b') as stream:
        deadline = time.monotonic()+timeout
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise ValueError('Python подготавливается другим процессом. Повторите запуск.') from None
                time.sleep(.05)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def slot_path(receipt, recorded=None):
    if recorded:
        slot = Path(recorded)
        if not slot.is_absolute() or slot.name != receipt['sha256']:
            raise ValueError('Некорректная папка Python в перечне установки.')
    else:
        slot = xdg_home('XDG_DATA_HOME')/'scottai/runtimes'/receipt['sha256']
    slot = Path(os.path.abspath(slot))
    no_links(slot)
    return slot


def ensure(root, recorded=None):
    """Return an absolute venv interpreter; preserve ready and partial owned slots."""
    if sys.platform != 'linux':
        raise ValueError('Отдельное окружение предназначено для Linux.')
    root = Path(root).resolve()
    source = root/'python-runtime'
    receipt = read_receipt(source)
    slot = slot_path(receipt, recorded)
    private_directory(slot.parent)
    with locked(slot.parent/('.'+slot.name+'.lock')):
        no_links(slot)
        owner = slot/OWNER
        expected = dict(schema=1, sha256=receipt['sha256'])
        if slot.exists():
            no_links(owner)
            try:
                metadata = json.loads(owner.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                raise ValueError('Папка Python не принадлежит ScottAI. Её содержимое сохранено.') from None
            if not isinstance(metadata, dict) or any(metadata.get(key) != value for key, value in expected.items()):
                raise ValueError('В папке Python находится другое окружение. Файлы сохранены.')
        else:
            private_directory(slot)
            metadata = dict(expected, ready=False)
            write_json(owner, metadata)
        base, runtime = slot/'python-runtime', slot/'runtime'
        no_links(base)
        no_links(runtime)
        if not base.exists():
            # Copy into an unpublished directory. Links in the vendor Python are
            # internal; retain them instead of duplicating 1000+ linked files.
            with tempfile.TemporaryDirectory(prefix='.python-copy-', dir=slot) as temporary:
                target = Path(temporary)/'python'
                for file in source.rglob('*'):
                    if file.is_symlink() and not file.resolve().is_relative_to(source.resolve()):
                        raise ValueError('Пакет Python содержит внешнюю ссылку.')
                shutil.copytree(source, target, symlinks=True)
                read_receipt(target)
                # A mounted image may have 0555 directories. Moving a directory
                # between parents needs write permission for its '..' entry.
                # This is our unpublished copy, never the mounted source.
                target.chmod(target.stat().st_mode | 0o700)
                executable = target/'bin/python3.13'
                executable.chmod(executable.stat().st_mode | 0o100)
                os.replace(target, base)
        if read_receipt(base) != receipt:
            raise ValueError('Постоянная база Python отличается от пакета. Файлы сохранены.')
        executable = runtime/'bin/python'
        no_links(runtime/'bin')
        no_links(runtime/'pyvenv.cfg')
        if metadata.get('ready') and (not executable.is_file() or not (runtime/'pyvenv.cfg').is_file()):
            metadata = dict(expected, ready=False)
            write_json(owner, metadata)
        if not metadata.get('ready'):
            # Use the final path: venv scripts contain absolute shebangs.
            subprocess.run([str(base/'bin/python3.13'), '-I', '-m', 'venv', str(runtime)], check=True)
        code = ('import json,sys; print(json.dumps(dict(base=sys.base_prefix, '
                'prefix=sys.prefix,version=list(sys.version_info[:2]))))')
        result = subprocess.run([str(executable), '-I', '-c', code], check=True,
                                capture_output=True, text=True, timeout=30)
        info = json.loads(result.stdout)
        if info != dict(base=str(base), prefix=str(runtime), version=[3, 13]):
            raise ValueError('Python использует другую базу. Повторите установку в отдельную папку.')
        if not metadata.get('ready'):
            write_json(owner, dict(expected, ready=True))
        return executable


def selected(root):
    """Select a recorded external slot or preserve a working legacy environment."""
    root = Path(root).resolve()
    metadata = json.loads((root/'.scott-linux-install.json').read_text(encoding='utf-8'))
    if not isinstance(metadata, dict):
        raise ValueError('Некорректный перечень установки ScottAI.')
    if metadata.get('runtime_home'):
        return ensure(root, metadata['runtime_home'])
    legacy = root/'runtime/bin/python'
    if metadata.get('runtime_owned') and legacy.is_file() and not (root/'runtime').is_symlink():
        return legacy
    return ensure(root)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(selected(args.root))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f'Не удалось подготовить Python: {error}\n')


if __name__ == '__main__':
    main()
