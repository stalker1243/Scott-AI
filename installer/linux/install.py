"""Per-user Linux installation. Preserve data and .env on upgrade/uninstall."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

SOURCE = Path(__file__).resolve().parent
# -I omits the script directory from sys.path. Use only our packaged stdlib
# helper; source checkouts keep it in the repository's backend directory.
_helpers = SOURCE/'backend'
if not (_helpers/'platform_paths.py').is_file() and SOURCE.name == 'linux' and SOURCE.parent.name == 'installer':
    _helpers = SOURCE.parent.parent/'backend'
if not (_helpers/'platform_paths.py').is_file():
    raise SystemExit('Пакет распакован не полностью: отсутствует backend/platform_paths.py. Распакуйте весь архив ScottAI в одну папку.')
sys.path.insert(0, str(_helpers))
from platform_paths import xdg_home, private_directory
from linux_runtime import ensure as ensure_external_runtime, slot_path, write_json

MARKER = '.scott-linux-install.json'
DIRECTORIES = ('launcher', 'lib', 'plugins', 'qml', 'libexec', 'translations',
               'backend', 'voice-assets', 'assets', 'licenses', 'python-runtime', 'docs')
FILES = ('VERSION.json', '.env.example', 'README.md', 'RELEASE-NOTES.md',
         'install.py', 'install.sh', 'uninstall.sh', 'run.sh', 'python-environment.sh')


def safe_prefix(path: Path, source: Path = SOURCE, uninstall: bool = False) -> Path:
    absolute = path.expanduser().absolute()
    if any(ord(character) < 32 or ord(character) == 127 for character in str(absolute)):
        raise ValueError('Путь не должен содержать управляющие символы.')
    if any(p.is_symlink() for p in (absolute, *absolute.parents)):
        raise ValueError('Папка установки и её родители не должны быть ссылками.')
    prefix = absolute.resolve()
    if prefix == Path(prefix.anchor) or prefix == Path.home().resolve() or (prefix/'.git').exists():
        raise ValueError('Выберите отдельную папку приложения.')
    if not uninstall and (prefix.is_relative_to(source) or source.is_relative_to(prefix)):
        raise ValueError('Папка установки должна находиться вне распакованного пакета.')
    if prefix.exists() and any(prefix.iterdir()) and not (prefix/MARKER).is_file():
        raise ValueError('Непустая папка не является установленным Scott AI; выберите другую.')
    return prefix


def payload_files(source: Path) -> list[Path]:
    result = [source/name for name in FILES if (source/name).is_file()]
    for name in DIRECTORIES:
        folder = source/name
        if folder.is_dir():
            result.extend(p for p in folder.rglob('*') if p.is_file() or p.is_symlink())
    for file in result:
        if not file.resolve().is_relative_to(source.resolve()):
            raise ValueError('Пакет содержит ссылку за пределы своей папки.')
        relative = file.relative_to(source)
        if is_user_data(relative):
            raise ValueError('Пакет содержит пользовательские данные.')
    return result


def is_user_data(path: Path) -> bool:
    return path.parts[:1] == ('data',) or path.parts[:2] == ('backend', 'data') or path.name == '.env'


def python_receipt(source: Path) -> dict:
    base = source/'python-runtime'
    receipt = json.loads((base/'.scott-python.json').read_text(encoding='utf-8'))
    required = {'bin/python3.13', 'lib/python3.13/os.py', 'lib/python3.13/venv/__init__.py'}
    if not str(receipt.get('version', '')).startswith('3.13.') or set(receipt.get('core', {})) != required:
        raise ValueError('В пакете отсутствует проверенный Python 3.13.')
    for name, sha in receipt['core'].items():
        file = base/name
        if not file.resolve().is_relative_to(base.resolve()) or hashlib.sha256(file.read_bytes()).hexdigest() != sha:
            raise ValueError('Файлы встроенного Python повреждены.')
    return receipt


def validate_environment(prefix: Path, previous: dict) -> None:
    runtime = prefix/'runtime'
    if runtime.is_symlink() and previous.get('runtime_home'):
        expected = Path(previous['runtime_home'])/'runtime'
        if expected.is_absolute() and runtime.readlink() == expected:
            # Only unlink this pointer on uninstall; never recursively remove
            # the independently owned, shared external environment.
            return
    if runtime.is_symlink() or not runtime.resolve().is_relative_to(prefix):
        raise ValueError('Runtime не должен быть ссылкой за пределы установки.')
    if runtime.exists() and not previous.get('runtime_owned'):
        raise ValueError('Существующая runtime не принадлежит установщику Scott AI.')
    if runtime.exists() and not runtime.is_dir():
        raise ValueError('Runtime должна быть отдельной папкой Python-окружения.')


def prepare_legacy_environment(prefix: Path, previous: dict, receipt: dict) -> None:
    validate_environment(prefix, previous)
    runtime = prefix/'runtime'
    replace = runtime.exists() and (previous.get('runtime_sha256') != receipt['sha256']
                                  or not (runtime/'pyvenv.cfg').is_file())
    backup = prefix/('.runtime-before-'+uuid.uuid4().hex) if replace else None
    if backup:
        runtime.rename(backup)
    try:
        subprocess.run([str(prefix/'python-runtime/bin/python3.13'), '-I', '-m', 'venv', str(runtime)], check=True)
    except (OSError, subprocess.CalledProcessError):
        if backup:
            if runtime.exists():
                shutil.rmtree(runtime)
            backup.rename(runtime)
        raise
    if backup:
        shutil.rmtree(backup)


def prepare_environment(prefix: Path, previous: dict, receipt: dict) -> None:
    runtime = prefix/'runtime'
    # Do not relocate ready venvs: entry points and native dependencies can
    # retain absolute paths. Existing installations keep their established base.
    if not previous.get('runtime_home') and runtime.exists():
        prepare_legacy_environment(prefix, previous, receipt)
        return
    recorded = previous.get('runtime_home') if previous.get('runtime_sha256') == receipt['sha256'] else None
    slot = slot_path(receipt, recorded)
    metadata = json.loads((prefix/MARKER).read_text(encoding='utf-8'))
    metadata.update(runtime_home=str(slot), runtime_sha256=receipt['sha256'])
    write_json(prefix/MARKER, metadata)
    python = ensure_external_runtime(prefix, str(slot))
    if runtime.is_symlink():
        runtime.unlink()
    elif runtime.exists():
        raise ValueError('Runtime изменился во время установки. Файлы сохранены.')
    runtime.symlink_to(python.parent.parent, target_is_directory=True)


def target_file(prefix: Path, name: str) -> Path:
    relative = Path(name)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Некорректный путь в перечне файлов установки.')
    target = prefix/relative
    if not target.parent.resolve().is_relative_to(prefix):
        raise ValueError('Путь установки выходит за пределы папки приложения.')
    return target


def default_prefix() -> Path:
    current = xdg_home('XDG_DATA_HOME')/'ScottAI'
    legacy = Path.home()/'.local/share/ScottAI'
    # Keep an existing installation's data when XDG changes between upgrades.
    if not (current/MARKER).is_file() and (legacy/MARKER).is_file():
        return legacy
    return current


def desktop_value(value: str) -> str:
    return value.replace('\\', '\\\\').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')


def desktop_exec(prefix: Path) -> str:
    quoted = str(prefix/'run.sh').replace('%', '%%')
    for symbol in ('\\', '"', '`', '$'):
        quoted = quoted.replace(symbol, '\\'+symbol)
    # Bash is a fixed executable, not a command string. The path is one literal
    # argument, so '=', spaces, percent codes and shell syntax remain filenames.
    return '/bin/bash '+desktop_value('"'+quoted+'"')


def owns_shortcut(shortcut: Path, prefix: Path) -> bool:
    if shortcut.name != 'com.scottai.launcher.desktop' or shortcut.is_symlink() or not shortcut.is_file():
        return False
    lines = shortcut.read_text(encoding='utf-8').splitlines()
    expected = 'X-ScottAI-InstallRoot='+desktop_value(str(prefix))
    if expected in lines and 'Exec='+desktop_exec(prefix) in lines:
        return True
    # Compatibility with the published 2.0.1 shortcut format.
    quoted = str(prefix/'run.sh')
    for symbol in ('\\', '"', '`', '$'):
        quoted = quoted.replace(symbol, '\\'+symbol)
    return 'Name=Scott AI' in lines and f'Exec="{quoted}"' in lines


def desktop_entry(prefix: Path) -> Path:
    shortcut = xdg_home('XDG_DATA_HOME')/'applications/com.scottai.launcher.desktop'
    private_directory(shortcut.parent)
    if shortcut.exists() or shortcut.is_symlink():
        if not owns_shortcut(shortcut, prefix):
            raise ValueError('Ярлык Scott AI принадлежит другой установке или изменён. Сохраните его либо используйте --no-shortcut.')
    text = ('[Desktop Entry]\nType=Application\nName=Scott AI\n'
            f'Exec={desktop_exec(prefix)}\nIcon={desktop_value(str(prefix/"assets/brand/icon-256.png"))}\n'
            f'X-ScottAI-InstallRoot={desktop_value(str(prefix))}\n'
            'Terminal=false\nCategories=Utility;\n')
    temporary = shortcut.with_name('.scott-desktop-'+uuid.uuid4().hex)
    try:
        with temporary.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, shortcut)
    finally:
        temporary.unlink(missing_ok=True)
    return shortcut


def install(prefix: Path, source: Path = SOURCE, shortcut: bool = True) -> None:
    prefix = safe_prefix(prefix, source)
    receipt = python_receipt(source)
    payload = payload_files(source)
    if not (source/'launcher/ScottAIQt').is_file():
        raise ValueError('В пакете отсутствует Qt-лаунчер.')
    prefix.mkdir(parents=True, exist_ok=True)
    marker = prefix/MARKER
    previous = json.loads(marker.read_text(encoding='utf-8')) if marker.exists() else {}
    validate_environment(prefix, previous)
    owned = set(previous.get('files', []))
    for file in payload:
        name = file.relative_to(source).as_posix()
        target = target_file(prefix, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            target.unlink()
        if file.is_symlink():
            target.unlink(missing_ok=True)
            target.symlink_to(file.readlink())
        else:
            shutil.copy2(file, target)
        owned.add(name)
    # Record ownership before a venv failure so installation can be retried safely.
    metadata = {'version': json.loads((source/'VERSION.json').read_text())['version'],
                'files': sorted(owned), 'runtime_owned': True,
                'shortcut': previous.get('shortcut', ''),
                'runtime_sha256': previous.get('runtime_sha256'),
                'runtime_home': previous.get('runtime_home')}
    write_json(marker, metadata)
    # Archives extracted by some file managers lose executable permission.
    # Restore only the known launchers and the checksum-verified interpreter.
    for name in ('python-runtime/bin/python3.13', 'launcher/ScottAIQt', 'run.sh', 'install.sh', 'uninstall.sh'):
        executable = target_file(prefix, name)
        if executable.is_file() and not executable.is_symlink():
            executable.chmod(executable.stat().st_mode | 0o100)
    prepare_environment(prefix, previous, receipt)
    metadata = json.loads(marker.read_text(encoding='utf-8'))
    metadata['runtime_sha256'] = receipt['sha256']
    write_json(marker, metadata)
    if shortcut:
        metadata['shortcut'] = str(desktop_entry(prefix))
        write_json(marker, metadata)
    print(f'Установлено: {prefix}\nЗапуск: {prefix}/run.sh')
    print('Библиотеки и модели речи подготовятся в окне первого запуска.')


def uninstall(prefix: Path, delete_data: bool = False) -> None:
    prefix = safe_prefix(prefix, uninstall=True)
    marker = prefix/MARKER
    if not marker.is_file():
        raise ValueError('В папке нет перечня установленного Scott AI.')
    metadata = json.loads(marker.read_text(encoding='utf-8'))
    shortcut = Path(metadata['shortcut']) if metadata.get('shortcut') else None
    if shortcut and shortcut.is_absolute() and owns_shortcut(shortcut, prefix):
        shortcut.unlink()
    for name in metadata['files']:
        file = target_file(prefix, name)
        if is_user_data(file.relative_to(prefix)):
            raise ValueError('Перечень удаления затрагивает рабочие данные.')
        file.unlink(missing_ok=True)
    runtime = prefix/'runtime'
    if metadata.get('runtime_owned') and (runtime.exists() or runtime.is_symlink()):
        if runtime.is_symlink():
            validate_environment(prefix, metadata)
            runtime.unlink()
        else:
            shutil.rmtree(runtime)
    if delete_data:
        for name in ('backend/data', 'data', 'audio_cache'):
            folder = target_file(prefix, name)
            if folder.is_symlink():
                folder.unlink()
            elif folder.is_dir():
                shutil.rmtree(folder)
        (prefix/'.env').unlink(missing_ok=True)
    metadata.update(files=[], runtime_owned=False, shortcut='')
    write_json(marker, metadata)
    print('Приложение удалено. ' + ('Данные в папке установки удалены. Отдельное XDG-хранилище пользователя сохранено.' if delete_data else 'История, вложения и настройки сохранены.'))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', type=Path, default=default_prefix())
    parser.add_argument('--no-shortcut', action='store_true')
    parser.add_argument('--uninstall', action='store_true')
    parser.add_argument('--delete-data', action='store_true')
    args = parser.parse_args()
    if sys.platform != 'linux' or sys.version_info < (3, 11):
        parser.error('Нужен Linux и Python 3.11 или новее.')
    if args.delete_data and not args.uninstall:
        parser.error('--delete-data используется только вместе с --uninstall.')
    if any(c in str(args.prefix) for c in '\n\r\t'):
        parser.error('Путь не должен содержать переносы строк или табуляцию.')
    try:
        if args.uninstall:
            uninstall(args.prefix, args.delete_data)
        else:
            install(args.prefix, shortcut=not args.no_shortcut)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'{error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
