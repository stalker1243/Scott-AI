"""Per-user Linux installation. Preserve data and .env on upgrade/uninstall."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

SOURCE = Path(__file__).resolve().parent
MARKER = '.scott-linux-install.json'
DIRECTORIES = ('launcher', 'lib', 'plugins', 'qml', 'libexec', 'translations',
               'backend', 'voice-assets', 'assets', 'licenses')
FILES = ('VERSION.json', '.env.example', 'README.md', 'RELEASE-NOTES.md',
         'install.py', 'install.sh', 'uninstall.sh', 'run.sh')


def safe_prefix(path: Path, source: Path = SOURCE, uninstall: bool = False) -> Path:
    absolute = path.expanduser().absolute()
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
        if 'data' in relative.parts or file.name == '.env':
            raise ValueError('Пакет содержит пользовательские данные.')
    return result


def target_file(prefix: Path, name: str) -> Path:
    relative = Path(name)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Некорректный путь в перечне файлов установки.')
    target = prefix/relative
    if not target.parent.resolve().is_relative_to(prefix):
        raise ValueError('Путь установки выходит за пределы папки приложения.')
    return target


def desktop_entry(prefix: Path) -> Path:
    shortcut = Path.home()/'.local/share/applications/com.scottai.launcher.desktop'
    shortcut.parent.mkdir(parents=True, exist_ok=True)
    quoted = str(prefix/'run.sh')
    for symbol in ('\\', '"', '`', '$'):
        quoted = quoted.replace(symbol, '\\'+symbol)
    shortcut.write_text('[Desktop Entry]\nType=Application\nName=Scott AI\n'
                        f'Exec="{quoted}"\nIcon={prefix}/assets/brand/icon-256.png\n'
                        'Terminal=false\nCategories=Utility;\n', encoding='utf-8')
    return shortcut


def install(prefix: Path, source: Path = SOURCE, shortcut: bool = True) -> None:
    prefix = safe_prefix(prefix, source)
    payload = payload_files(source)
    if not (source/'launcher/ScottAIQt').is_file():
        raise ValueError('В пакете отсутствует Qt-лаунчер.')
    prefix.mkdir(parents=True, exist_ok=True)
    marker = prefix/MARKER
    previous = json.loads(marker.read_text(encoding='utf-8')) if marker.exists() else {}
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
    runtime = prefix/'runtime'
    if runtime.is_symlink():
        raise ValueError('Runtime не должен быть ссылкой.')
    if runtime.exists() and not (runtime/'pyvenv.cfg').is_file() and not previous.get('runtime_owned'):
        raise ValueError('Существующая runtime не является Python-окружением.')
    # Record ownership before a venv failure so installation can be retried safely.
    metadata = {'version': json.loads((source/'VERSION.json').read_text())['version'],
                'files': sorted(owned), 'runtime_owned': True,
                'shortcut': previous.get('shortcut', '')}
    marker.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    # Re-running venv also repairs a previous failure during ensurepip.
    subprocess.run([sys.executable, '-m', 'venv', str(runtime)], check=True)
    if shortcut:
        metadata['shortcut'] = str(desktop_entry(prefix))
        marker.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print(f'Установлено: {prefix}\nЗапуск: {prefix}/run.sh')
    print('Библиотеки и модели речи подготовятся в окне первого запуска.')


def uninstall(prefix: Path, delete_data: bool = False) -> None:
    prefix = safe_prefix(prefix, uninstall=True)
    marker = prefix/MARKER
    if not marker.is_file():
        raise ValueError('В папке нет перечня установленного Scott AI.')
    metadata = json.loads(marker.read_text(encoding='utf-8'))
    shortcut = Path(metadata['shortcut']) if metadata.get('shortcut') else None
    expected = Path.home()/'.local/share/applications/com.scottai.launcher.desktop'
    if shortcut == expected and shortcut.is_file():
        if str(prefix/'run.sh') in shortcut.read_text(encoding='utf-8'):
            shortcut.unlink()
    for name in metadata['files']:
        file = target_file(prefix, name)
        if 'data' in file.relative_to(prefix).parts or file.name == '.env':
            raise ValueError('Перечень удаления затрагивает рабочие данные.')
        file.unlink(missing_ok=True)
    runtime = prefix/'runtime'
    if metadata.get('runtime_owned') and runtime.exists():
        if runtime.is_symlink():
            raise ValueError('Runtime заменён ссылкой; удаление отменено.')
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
    marker.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print('Приложение удалено. ' + ('Данные удалены.' if delete_data else 'История, вложения и настройки сохранены.'))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', type=Path, default=Path.home()/'.local/share/ScottAI')
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
        parser.exit(1, f'{error}\nДля создания Python-окружения может потребоваться пакет python3-venv.\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
