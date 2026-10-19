"""Build an x86-64 AppImage from a clean Linux package, with pinned tools.

Run on Linux after build_linux.py. The runtime is static and the build itself
works without FUSE. No backend libraries, models or personal files are bundled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TOOLS = {
    'appimagetool.AppImage': (
        'https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage',
        'ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0'),
    'runtime-x86_64': (
        'https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64',
        '2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d'),
}
DIRECTORIES = frozenset(('launcher', 'bin', 'lib', 'plugins', 'qml', 'python-runtime',
                         'backend', 'voice-assets', 'docs', 'assets', 'licenses'))
FILES = frozenset(('.env.example', 'README.md', 'RELEASE-NOTES.md', 'VERSION.json', 'LICENSE',
                   'check_backend.py', 'check_distribution.sh', 'check_package.py',
                   'check_runtime.py', 'check_wayland.py', 'check_appimage.py',
                   'install.py', 'install.sh', 'uninstall.sh', 'run.sh', 'python-environment.sh'))


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate_package(package):
    """Reject installed/source trees, private stores and external vendor links."""
    package = Path(package).resolve(strict=True)
    required = ('launcher/ScottAIQt', 'launcher/ScottAIUpdater', 'launcher/qt.conf',
                'backend/linux_runtime.py', 'backend/storage_paths.py',
                'backend/update_package.py', 'backend/update_appimage.py', 'python-runtime/.scott-python.json',
                'run.sh', 'python-environment.sh', 'assets/brand/icon-256.png', 'VERSION.json')
    if not all((package/name).is_file() for name in required):
        raise ValueError('Expected a complete Linux Qt distribution.')
    for file in package.iterdir():
        if file.name not in DIRECTORIES | FILES:
            raise ValueError('Unknown distribution entry: '+file.name)
        if file.name in DIRECTORIES and not file.is_dir():
            raise ValueError('Expected a distribution directory: '+file.name)
    for file in package.rglob('*'):
        if file.is_symlink():
            if not file.resolve(strict=True).is_relative_to(package):
                raise ValueError('External link in the distribution: '+str(file.relative_to(package)))
        elif not (file.is_dir() or file.is_file()):
            raise ValueError('Unsupported distribution entry.')
        relative = file.relative_to(package)
        if (relative.parts[:2] == ('backend', 'data') or '__pycache__' in relative.parts
                or file.name == '.env' or file.suffix in ('.pyc', '.log', '.sqlite', '.db')):
            raise ValueError('Private or generated file in the distribution: '+str(relative))
    metadata = json.loads((package/'VERSION.json').read_text(encoding='utf-8'))
    version = metadata['version']
    import re
    if not isinstance(version, str) or not re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,3}', version):
        raise ValueError('Invalid package version.')
    return version


def tools(cache, offline=False):
    cache = Path(cache).absolute()
    if any(p.is_symlink() for p in (cache, *cache.parents)):
        raise ValueError('Tool cache must not contain symbolic links.')
    cache.mkdir(parents=True, exist_ok=True)
    for name, (url, expected) in TOOLS.items():
        target = cache/name
        if target.is_symlink():
            raise ValueError('Linked build tool: '+name)
        if target.is_file():
            if digest(target) != expected:
                raise ValueError('Cached build tool checksum mismatch: '+name)
        elif offline:
            raise ValueError('Missing pinned build tool in offline mode: '+name)
        else:
            with tempfile.NamedTemporaryFile(dir=cache, prefix='.download-', delete=False) as stream:
                temporary = Path(stream.name)
                try:
                    with urllib.request.urlopen(url, timeout=60) as response:
                        shutil.copyfileobj(response, stream)
                    stream.close()
                    if digest(temporary) != expected:
                        raise ValueError('Downloaded build tool checksum mismatch: '+name)
                    os.replace(temporary, target)
                finally:
                    temporary.unlink(missing_ok=True)
        target.chmod(0o755)
    return cache


def build(package, output, cache, *, offline=False, jobs=4):
    package, output = Path(package).resolve(), Path(output).absolute()
    version = validate_package(package)
    if output.suffix != '.AppImage':
        raise ValueError('Output must have the .AppImage extension.')
    if not 1 <= jobs <= 16:
        raise ValueError('Jobs must be between 1 and 16.')
    if output.exists() or output.is_symlink():
        raise ValueError('Output already exists; refusing to overwrite it.')
    if output.with_suffix('.AppImage.sha256').exists():
        raise ValueError('Output checksum already exists.')
    if output.is_relative_to(package) or any(p.is_symlink() for p in output.parents):
        raise ValueError('Output must be outside the package, without linked parents.')
    cache = tools(cache, offline)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Keep the AppDir on a native Linux filesystem. A Windows/shared output
    # volume cannot represent CPython's case-sensitive terminfo vendor links.
    with tempfile.TemporaryDirectory(prefix='.appimage-build-') as temporary:
        work = Path(temporary)
        appdir = work/'ScottAI.AppDir'
        shutil.copytree(package, appdir, symlinks=True)
        (appdir/'.scott-linux-install.json').write_text('{"image_layout":1}\n', encoding='utf-8')
        shutil.copy2(ROOT/'installer/linux/AppRun', appdir/'AppRun')
        (appdir/'AppRun').chmod(0o755)
        shutil.copy2(ROOT/'installer/linux/com.scottai.launcher.desktop',
                     appdir/'com.scottai.launcher.desktop')
        shutil.copy2(appdir/'assets/brand/icon-256.png', appdir/'scottai.png')
        (appdir/'.DirIcon').symlink_to('scottai.png')
        licenses = appdir/'licenses/appimage'
        shutil.copytree(ROOT/'installer/licenses/appimage', licenses, dirs_exist_ok=True)
        # The tool is an AppImage too. Extract once into our own temporary dir;
        # neither building nor running its squashfs utility requires FUSE.
        subprocess.run([str(cache/'appimagetool.AppImage'), '--appimage-extract'],
                       cwd=work, check=True, stdout=subprocess.DEVNULL)
        env = dict(os.environ, ARCH='x86_64', VERSION=version)
        staged = work/'ScottAI.AppImage'
        subprocess.run([str(work/'squashfs-root/AppRun'), '--no-appstream', '--comp', 'zstd',
                        '--mksquashfs-opt', '-processors', '--mksquashfs-opt', str(jobs),
                        '--runtime-file', str(cache/'runtime-x86_64'), str(appdir), str(staged)],
                       check=True, env=env)
        staged.chmod(0o755)
        # Stage on the destination filesystem, then publish without clobbering
        # a concurrently created file (the build temp may be on another disk).
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix='.image-', delete=False) as stream:
            pending = Path(stream.name)
            try:
                with staged.open('rb') as image:
                    shutil.copyfileobj(image, stream)
                stream.flush()
                os.fsync(stream.fileno())
                pending.chmod(0o755)
                os.link(pending, output)
            finally:
                pending.unlink(missing_ok=True)
    sha = digest(output)
    with output.with_suffix('.AppImage.sha256').open('x', encoding='ascii') as stream:
        stream.write(f'{sha}  {output.name}\n')
    result = dict(artifact=str(output), bytes=output.stat().st_size, sha256=sha,
                  version=version, tools={name: value[1] for name, value in TOOLS.items()})
    print(json.dumps(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tools-cache', type=Path, default=ROOT/'installer/.cache/appimage')
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    if sys.platform != 'linux' or platform.machine() != 'x86_64':
        parser.error('Build the AppImage on Linux x86-64.')
    for command in ('file', 'desktop-file-validate'):
        if not shutil.which(command):
            parser.error('Install file and desktop-file-utils before building an AppImage.')
    try:
        build(args.package, args.output, args.tools_cache, offline=args.offline, jobs=args.jobs)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, str(error)+'\n')


if __name__ == '__main__':
    main()
