"""
Сборка дистрибутива Scott AI.

Складывает в одну папку всё, что нужно для работы на чужом компьютере:
встроенный Python, код backend и собранный лаунчер. Получившуюся папку можно
упаковать установщиком или просто заархивировать.

Чего здесь намеренно НЕТ — тяжёлых зависимостей. torch со сборкой под
видеокарту весит 3.9 ГБ, модели распознавания и синтеза — ещё 700 МБ. Класть
их в дистрибутив бессмысленно по двум причинам: такой архив никто не станет
скачивать, и он всё равно оказался бы неправильным для половины машин — сборка
torch зависит от того, есть ли в компьютере видеокарта NVIDIA. Поэтому они
ставятся при первом запуске, когда уже известно, куда именно ставим
(см. backend/bootstrap.py).

Запуск:

    python installer/build.py                # Qt: installer/dist-qt
    python installer/build.py --clean        # предварительно очистив
    python installer/build.py --installer    # и упаковать в установочный .exe
    python installer/build.py --launcher avalonia --installer  # прежний интерфейс
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "installer"
DIST = INSTALLER / "dist"
CACHE = INSTALLER / ".cache"

PYTHON_VERSION = "3.13.7"
PYTHON_EMBED_URL = (
    f"https://www.python.org/ftp/python/{PYTHON_VERSION}/"
    f"python-{PYTHON_VERSION}-embed-amd64.zip"
)
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"

# Что из backend попадает в дистрибутив. Перечислено явно, а не «всё подряд»:
# рядом лежат логи, кэш и данные конкретной машины, которым на чужом компьютере
# делать нечего.
BACKEND_FILES = [
    "*.py",
    "requirements.txt",
    "pytest.ini",
]

BACKEND_SKIP = {"__pycache__", "tests", "logs", "data"}


def log(message: str) -> None:
    print(f"  {message}")


def download(url: str, target: Path) -> Path:
    """Скачать файл, если его ещё нет в кэше сборки."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        log(f"уже скачано: {target.name}")
        return target

    log(f"скачиваю {url}")
    urllib.request.urlretrieve(url, target)
    return target


def prepare_python(dest: Path) -> None:
    """
    Положить встроенный Python и научить его видеть установленные пакеты.

    Встроенная сборка нарочно урезана: в ней нет pip, а файл ._pth ограничивает
    пути поиска модулей так, что site-packages игнорируется. Обе вещи
    приходится включать вручную — иначе поставить зависимости будет некуда.
    """
    archive = download(PYTHON_EMBED_URL, CACHE / f"python-{PYTHON_VERSION}-embed.zip")

    runtime = dest / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(runtime)

    pth = next(runtime.glob("python*._pth"), None)
    if pth is None:
        raise RuntimeError("во встроенном Python не нашёлся файл ._pth")

    text = pth.read_text(encoding="utf-8")
    text = text.replace("#import site", "import site")
    # Папка backend — в путях поиска: встроенная сборка не добавляет каталог
    # запускаемого скрипта сама, и любой импорт соседнего модуля падает.
    if "..\\backend" not in text:
        text = text.replace(".\n", ".\n..\\backend\n", 1)
    if "Lib\\site-packages" not in text:
        text = text.replace("python313.zip", "python313.zip\nLib\\site-packages", 1)
    pth.write_text(text, encoding="utf-8")

    get_pip = download(GET_PIP_URL, CACHE / "get-pip.py")
    shutil.copy2(get_pip, runtime / "get-pip.py")

    log("встроенный Python готов (pip доустанавливается при первом запуске)")


def copy_backend(dest: Path) -> None:
    """Скопировать код backend без данных конкретной машины."""
    target = dest / "backend"
    target.mkdir(parents=True, exist_ok=True)

    source = ROOT / "backend"
    for pattern in BACKEND_FILES:
        for item in source.glob(pattern):
            if item.name in BACKEND_SKIP or not item.is_file():
                continue
            shutil.copy2(item, target / item.name)

    log(f"backend скопирован: {len(list(target.glob('*.py')))} модулей")


def copy_voice_assets(dest: Path) -> None:
    """Only the optional worker and synthetic reference; no weights or personal data."""
    import importlib.util
    spec = importlib.util.spec_from_file_location('voice_install_builder', ROOT/'backend/scott_voice_install.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    target = dest/'voice-assets'
    if target.exists():
        current = module.asset_sources(ROOT)
        previous = module.asset_sources(dest)
        if any(module.checksum(current[name]) != module.checksum(previous[name]) for name in module.ASSETS):
            raise RuntimeError('Пакет Scott Voice изменился; пересоберите установщик с --clean.')
        log('пакет Scott Voice уже проверен')
        return
    result = module.bundle_assets(target, ROOT)
    log(f"пакет Scott Voice: {result['files']} файлов, {result['bytes']/1024:.0f} КиБ; веса ставятся отдельно")


def build_qt_launcher(dest: Path, qt_root: Path, compiler_root: Path) -> None:
    project = ROOT / 'ScottAI_qt'
    output = dest / 'launcher'
    output.mkdir(parents=True, exist_ok=True)
    tool = qt_root / 'bin' / 'windeployqt.exe'
    if not tool.is_file() or not (compiler_root / 'bin' / 'g++.exe').is_file():
        raise RuntimeError('Не найден Qt / MinGW. Укажите --qt-root и --compiler-root')
    subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(project / 'build.ps1'),
                    '-QtRoot', str(qt_root), '-CompilerRoot', str(compiler_root)], check=True, cwd=ROOT)
    executable = output / 'ScottAIQt.exe'
    shutil.copy2(project / 'build' / 'ScottAIQt.exe', executable)
    environment = dict(os.environ)
    environment['PATH'] = str(compiler_root / 'bin') + os.pathsep + str(qt_root / 'bin') + os.pathsep + environment.get('PATH', '')
    subprocess.run([str(tool), '--release', '--no-translations', '--compiler-runtime', '--qmldir', str(project),
                    '--dir', str(output), str(executable)], check=True, env=environment, cwd=ROOT)
    licenses = dest/'licenses'
    shutil.copytree(INSTALLER/'licenses',licenses,dirs_exist_ok=True)
    sbom = qt_root/'sbom'
    if sbom.is_dir():
        shutil.copytree(sbom,licenses/'qt-sbom',dirs_exist_ok=True)
    log(f'Qt-лаунчер и библиотеки подготовлены: {output}')


def build_launcher(dest: Path) -> None:
    """
    Собрать лаунчер так, чтобы он не требовал установленного .NET.

    self-contained добавляет к размеру около семидесяти мегабайт, но избавляет
    пользователя от отдельной установки среды — ровно то, ради чего затевался
    установщик.
    """
    project = ROOT / "ScottAI_avalonia"
    output = dest / "launcher"

    log("собираю лаунчер (self-contained, это займёт минуту)…")
    result = subprocess.run(
        [
            "dotnet", "publish", str(project),
            "-c", "Release",
            "-r", "win-x64",
            "--self-contained", "true",
            "-p:PublishSingleFile=true",
            "-o", str(output),
        ],
        capture_output=True, text=True, timeout=900,
    )

    if result.returncode != 0:
        raise RuntimeError(f"не удалось собрать лаунчер:\n{result.stdout[-2000:]}")

    log(f"лаунчер собран: {output}")


def copy_extras(dest: Path) -> None:
    """Файлы, которые пользователь должен увидеть рядом с программой."""
    # VERSION.json обязателен: по нему программа понимает, какая версия
    # установлена. Без него она считает свою версию нулевой и предлагает
    # обновиться на ту, что уже стоит.
    for name in (".env.example", "README.md", "VERSION.json", "LICENSE"):
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, dest / name)
    notes = ROOT/'docs'/f'release-notes-{read_version()}.md'
    if notes.is_file():
        shutil.copy2(notes,dest/'RELEASE-NOTES.md')

    log("сопроводительные файлы скопированы")


def report_size(dest: Path) -> None:
    total = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
    log(f"размер дистрибутива: {total / 1024 ** 2:.0f} МБ")
    log("(torch и модели — ещё около 4.5 ГБ — ставятся при первом запуске)")


def read_version() -> str:
    """
    Номер версии из VERSION.json — единственного места, где он записан.

    Тот же файл читает backend (`/api/version/current`), и расхождение между
    номером в установщике и номером внутри программы означало бы, что проверка
    обновлений врёт.
    """
    version_file = ROOT / "VERSION.json"
    try:
        with open(version_file, encoding="utf-8") as f:
            return json.load(f).get("version", "0.0.0")
    except Exception as e:
        log(f"не смог прочитать VERSION.json ({e}) — беру 0.0.0")
        return "0.0.0"


def find_iscc() -> Optional[Path]:
    """
    Где лежит компилятор Inno Setup.

    winget ставит его в папку пользователя, а установщик с сайта — в
    Program Files; проверяются оба места, потому что заранее неизвестно,
    каким способом его поставили.
    """
    candidates = [
        CACHE / 'inno' / 'ISCC.exe',
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    found = shutil.which("ISCC.exe")
    return Path(found) if found else None


def build_installer(dest: Path, app_exe: str = 'ScottAI.exe') -> bool:
    """Упаковать готовый дистрибутив в один установочный .exe."""
    iscc = find_iscc()
    if iscc is None:
        log("не нашёл Inno Setup — установщик не собран")
        log("поставить: winget install --id JRSoftware.InnoSetup")
        return False

    version = read_version()
    if not (INSTALLER / 'assets' / 'wizard-sidebar.bmp').is_file():
        subprocess.run(['powershell.exe', '-NoProfile', '-File', str(INSTALLER / 'export_wizard_art.ps1')], check=True)
    script = INSTALLER / "scott.iss"
    release = INSTALLER / "release"
    release.mkdir(parents=True, exist_ok=True)

    log(f"упаковываю установщик {version} (сжатие занимает пару минут)…")
    result = subprocess.run(
        [
            str(iscc),
            f"/DAppVersion={version}",
            f"/DDistDir={dest}",
            f"/DOutputDir={release}",
            f"/DAppExe={app_exe}",
            str(script),
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(INSTALLER),
    )

    if result.returncode != 0:
        log("Inno Setup вернул ошибку:")
        print(result.stdout[-2000:])
        print(result.stderr[-1000:])
        return False

    package = release / f"ScottAI-{version}{'-Qt' if app_exe == 'ScottAIQt.exe' else ''}-setup.exe"
    if package.exists():
        log(f"установщик готов: {package} ({package.stat().st_size / 1024 ** 2:.0f} МБ)")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Собрать дистрибутив Scott AI")
    parser.add_argument("--clean", action="store_true", help="очистить папку сборки перед началом")
    parser.add_argument("--skip-launcher", action="store_true", help="не собирать лаунчер (быстрее для проверки)")
    parser.add_argument("--installer", action="store_true", help="упаковать результат в установочный .exe")
    parser.add_argument('--launcher', choices=['qt', 'avalonia'], default='qt', help='лаунчер для Windows (по умолчанию Qt)')
    parser.add_argument('--qt-root', type=Path, default=Path(r'C:\Qt\6.11.2\mingw_64'))
    parser.add_argument('--compiler-root', type=Path, default=Path(r'C:\Qt\Tools\mingw1310_64'))
    parser.add_argument('--output', type=Path, help='новая папка дистрибутива внутри проекта; не перезаписывает существующую')
    args = parser.parse_args()
    destination = INSTALLER / 'dist-qt' if args.launcher == 'qt' else DIST
    if args.output is not None:
        destination = args.output.resolve()
        if not destination.is_relative_to(ROOT.resolve()) or destination==ROOT.resolve():
            parser.error('--output должен находиться внутри проекта')
        if destination.exists():
            parser.error('--output уже существует; выберите новую папку')
        if args.clean:
            parser.error('--output создаёт новую папку и не требует --clean')

    if args.clean and destination.exists():
        if destination.resolve().parent != INSTALLER.resolve():
            raise RuntimeError('Папка сборки должна находиться внутри installer')
        shutil.rmtree(destination)
        log("папка сборки очищена")

    destination.mkdir(parents=True, exist_ok=True)

    print("Собираю дистрибутив Scott AI")
    prepare_python(destination)
    copy_backend(destination)
    copy_voice_assets(destination)
    copy_extras(destination)
    if not args.skip_launcher:
        if args.launcher == 'qt':
            build_qt_launcher(destination, args.qt_root, args.compiler_root)
        else:
            build_launcher(destination)
    report_size(destination)

    if args.installer and not build_installer(destination, 'ScottAIQt.exe' if args.launcher == 'qt' else 'ScottAI.exe'):
        return 1

    print(f"\nГотово: {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
