"""Replace one owned AppImage atomically; keep its previous inode as a backup.

Only stdlib. The Qt helper calls this after its parent has exited. Paths and
identity come from the running image, never from an archive's contents.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import uuid

LIMIT = 2 * 1024**3
IDENTITY = ('device', 'inode', 'size', 'mtime_ns')


def no_links(path):
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Путь образа содержит ссылку или не является абсолютным.')


def identity(info):
    return dict(zip(IDENTITY, map(str, (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns))))


def image_header(stream):
    stream.seek(0)
    head = stream.read(64)
    if (len(head) != 64 or head[:6] != b'\x7fELF\x02\x01' or head[8:11] != b'AI\x02'
            or head[18:20] != b'\x3e\x00'):
        raise ValueError('Файл не является AppImage x86-64 типа 2.')


def snapshot(path):
    path = Path(path)
    no_links(path)
    info = path.stat(follow_symlinks=False)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
            or not 64 <= info.st_size <= LIMIT or info.st_mode & 0o7000):
        raise ValueError('Для обновления нужен обычный AppImage, принадлежащий пользователю.')
    with path.open('rb') as stream:
        image_header(stream)
    return dict(path=str(path), **identity(info))


def metadata(image, directory):
    # This executable is already checksum-verified. Ask only its static runtime
    # to extract two metadata files; do not start Qt, backend or a mounted image.
    env = {k: v for k, v in os.environ.items()
           if k not in ('TARGET_APPIMAGE', 'APPIMAGE', 'APPDIR', 'ARGV0', 'APPIMAGE_EXTRACT_AND_RUN',
                        'LD_LIBRARY_PATH', 'LD_PRELOAD', 'PYTHONHOME', 'PYTHONPATH')}
    for name in ('VERSION.json', '.scott-linux-install.json'):
        subprocess.run([str(image), '--appimage-extract', name], cwd=directory, env=env,
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30)
    root = Path(directory)/'squashfs-root'
    values = []
    for name in ('VERSION.json', '.scott-linux-install.json'):
        file = root/name
        no_links(file)
        if not file.is_file() or file.stat().st_size > 32768:
            raise ValueError('Некорректные метаданные AppImage.')
        values.append(json.loads(file.read_text(encoding='utf-8')))
    return values


def apply(archive, sha256, version, expected):
    import fcntl
    if not re.fullmatch('[a-f0-9]{64}', sha256) or not re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,3}', version):
        raise ValueError('Некорректная версия или контрольная сумма.')
    if (not isinstance(expected, dict) or not isinstance(expected.get('path'), str)
            or any(not isinstance(expected.get(k), str) or not expected[k].isdigit() for k in IDENTITY)):
        raise ValueError('Отсутствует исходная идентичность AppImage.')
    target = Path(expected['path'])
    if snapshot(target) != {k: expected[k] for k in ('path', *IDENTITY)}:
        raise ValueError('Исходный AppImage уже изменился. Файлы сохранены; запустите текущий образ.')
    archive = Path(archive).absolute()
    no_links(archive)
    parent = target.parent
    directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    old = staged_fd = None
    staged = '.scott-update-'+uuid.uuid4().hex+'.AppImage'
    backup = '.scott-previous-'+uuid.uuid4().hex+'.AppImage'
    linked = committed = False

    def unchanged(links=1):
        no_links(target)
        info = os.stat(target.name, dir_fd=directory, follow_symlinks=False)
        if identity(info) != {k: expected[k] for k in IDENTITY} or info.st_nlink != links:
            raise ValueError('Исходный AppImage изменился во время обновления. Файлы сохранены.')
        current = parent.stat(follow_symlinks=False)
        held = os.fstat(directory)
        if (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino):
            raise ValueError('Папка образа изменилась во время обновления.')

    def remove_owned(name, descriptor):
        try:
            entry = os.stat(name, dir_fd=directory, follow_symlinks=False)
            held = os.fstat(descriptor)
            if (entry.st_dev, entry.st_ino) == (held.st_dev, held.st_ino):
                os.unlink(name, dir_fd=directory)
        except FileNotFoundError:
            pass

    try:
        old = os.open(target.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        fcntl.flock(old, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if identity(os.fstat(old)) != {k: expected[k] for k in IDENTITY}:
            raise ValueError('Исходный AppImage уже заменён другим процессом.')
        unchanged()
        size = archive.stat().st_size
        if not 64 <= size <= LIMIT or shutil.disk_usage(parent).free < size + 16*1024**2:
            raise ValueError('Недостаточно места для нового образа или неверный размер файла.')
        staged_fd = os.open(staged, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        digest = hashlib.sha256()
        total = 0
        with archive.open('rb') as source, os.fdopen(os.dup(staged_fd), 'wb') as output:
            while block := source.read(1024**2):
                total += len(block)
                if total > LIMIT:
                    raise ValueError('Образ обновления слишком велик.')
                digest.update(block)
                output.write(block)
            output.flush()
            os.fsync(output.fileno())
        if total != size or digest.hexdigest() != sha256:
            raise ValueError('Контрольная сумма обновления не совпала.')
        with os.fdopen(os.dup(staged_fd), 'rb') as stream:
            image_header(stream)
        os.fchmod(staged_fd, (stat.S_IMODE(os.fstat(old).st_mode) & 0o777) | 0o100)
        os.fsync(staged_fd)
        # Linux refuses exec while any descriptor is open for writing (ETXTBSY).
        readonly = os.open(staged, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        os.close(staged_fd)
        staged_fd = readonly
        with tempfile.TemporaryDirectory(prefix='scott-image-metadata-') as temporary:
            release, layout = metadata(parent/staged, temporary)
        if (not isinstance(release, dict) or release.get('version') != version
                or not isinstance(layout, dict) or layout.get('image_layout') != 1):
            raise ValueError('Версия или формат AppImage не совпали с выбранным обновлением.')
        unchanged()
        os.link(target.name, backup, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
        linked = True
        unchanged(links=2)
        os.replace(staged, target.name, src_dir_fd=directory, dst_dir_fd=directory)
        committed = True
        result = dict(updated=True, backup=str(parent/backup), sha256=sha256)
        try:
            os.fsync(directory)
        except OSError:
            # The atomic replacement already happened. Retrying with the old
            # identity would be wrong; retain the backup and report the warning.
            result['warning'] = 'Образ заменён, но синхронизация папки не удалась. Резервная копия сохранена.'
        return result
    finally:
        if staged_fd is not None:
            if not committed:
                remove_owned(staged, staged_fd)
            os.close(staged_fd)
        if linked and not committed:
            remove_owned(backup, old)
        if old is not None:
            os.close(old)
        os.close(directory)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'sha256', 'version', 'job'):
        parser.add_argument('--'+name, required=True)
    args = parser.parse_args()
    try:
        job = json.loads(Path(args.job).read_text(encoding='utf-8'))
        print(json.dumps(apply(args.archive, args.sha256, args.version, job.get('image')), ensure_ascii=False))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, str(error)+'\n')
