"""
Сборка дистрибутива Scott AI для Linux.

Отличия от Windows-сборки принципиальные, поэтому это отдельный скрипт:

  * встроенного Python для Linux не существует (embeddable-сборка бывает только
    под Windows), поэтому используется системный, а зависимости ставятся в
    виртуальное окружение — его создаёт install.sh при установке;

  * вместо установщика — обычный архив со скриптом: он работает в любом
    дистрибутиве, тогда как .deb годился бы только для Debian и Ubuntu;

  * лаунчер собирается кросс-компиляцией (`-r linux-x64`), прямо отсюда,
    с Windows — .NET это умеет.

Запуск:

    python installer/build_linux.py            # собрать в installer/dist-linux
    python installer/build_linux.py --clean    # предварительно очистив
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "installer"
DIST = INSTALLER / "dist-linux"
RELEASE = INSTALLER / "release"

# Что из backend попадает в дистрибутив. Перечислено явно, а не «всё подряд»:
# рядом лежат логи, кэш и данные конкретной машины, которым на чужом
# компьютере делать нечего.
BACKEND_FILES = ["*.py", "requirements.txt", "pytest.ini"]
BACKEND_SKIP = {"__pycache__", "tests", "logs", "data"}


def log(message: str) -> None:
    print(f"  {message}")


def read_version() -> str:
    """Номер версии из VERSION.json — того же файла, что читает backend."""
    try:
        with open(ROOT / "VERSION.json", encoding="utf-8") as f:
            return json.load(f).get("version", "0.0.0")
    except Exception as e:
        log(f"не смог прочитать VERSION.json ({e}) — беру 0.0.0")
        return "0.0.0"


def build_launcher(dest: Path) -> None:
    """
    Собрать лаунчер под Linux.

    self-contained: .NET на машине человека не нужен, всё внутри. Плюс к
    размеру около семидесяти мегабайт, зато не приходится объяснять, как
    ставить среду выполнения.
    """
    project = ROOT / "ScottAI_avalonia" / "ScottAI.Avalonia.csproj"
    target = dest / "launcher"

    log("собираю лаунчер под linux-x64 (это займёт минуту)…")
    subprocess.run(
        [
            "dotnet", "publish", str(project),
            "-c", "Release",
            "-r", "linux-x64",
            "--self-contained", "true",
            "-o", str(target),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    # Отладочные символы в дистрибутиве не нужны — это десятки мегабайт.
    for pdb in target.glob("*.pdb"):
        pdb.unlink()

    log(f"лаунчер собран: {target}")


def copy_backend(dest: Path) -> None:
    source = ROOT / "backend"
    target = dest / "backend"
    target.mkdir(parents=True, exist_ok=True)

    count = 0
    for pattern in BACKEND_FILES:
        for item in source.glob(pattern):
            if item.is_file() and item.parent.name not in BACKEND_SKIP:
                shutil.copy2(item, target / item.name)
                count += 1

    log(f"backend скопирован: {count} файлов")


def copy_extras(dest: Path) -> None:
    """Сопроводительные файлы, скрипт установки и иконка."""
    for name in (".env.example", "README.md", "VERSION.json"):
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, dest / name)

    installer_script = INSTALLER / "linux" / "install.sh"
    target = dest / "install.sh"
    shutil.copy2(installer_script, target)

    # Права на исполнение внутри архива выставляются при упаковке, но на всякий
    # случай ставим их и файлу: если человек распакует архив штатным
    # менеджером, флаг сохранится.
    target.chmod(0o755)

    icon = ROOT / "ScottAI_avalonia" / "Assets" / "icon-256.png"
    if icon.exists():
        shutil.copy2(icon, dest / "scott.png")

    log("сопроводительные файлы скопированы")


def pack(dest: Path, version: str) -> Path:
    """
    Упаковать в tar.gz.

    Права на исполнение проставляются здесь: на Windows их нет как понятия, и
    без этого распакованный на Linux лаунчер не запустился бы, а install.sh
    пришлось бы вызывать через «bash install.sh».
    """
    RELEASE.mkdir(parents=True, exist_ok=True)
    archive_path = RELEASE / f"ScottAI-{version}-linux-x64.tar.gz"

    executables = {"install.sh", "uninstall.sh", "ScottAI", "createdump"}

    def prepare(item: tarfile.TarInfo) -> tarfile.TarInfo:
        name = Path(item.name).name
        if name in executables or name.endswith(".so"):
            item.mode = 0o755
        elif item.isdir():
            item.mode = 0o755
        else:
            item.mode = 0o644
        return item

    log("упаковываю архив…")
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(dest, arcname=f"ScottAI-{version}", filter=prepare)

    size = archive_path.stat().st_size / 1024 ** 2
    log(f"архив готов: {archive_path} ({size:.0f} МБ)")
    return archive_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Собрать дистрибутив Scott AI для Linux")
    parser.add_argument("--clean", action="store_true", help="очистить папку сборки перед началом")
    parser.add_argument("--skip-launcher", action="store_true", help="не собирать лаунчер (быстрее для проверки)")
    args = parser.parse_args()

    if args.clean and DIST.exists():
        shutil.rmtree(DIST)
        log("папка сборки очищена")

    DIST.mkdir(parents=True, exist_ok=True)

    version = read_version()
    print(f"Собираю дистрибутив Scott AI {version} для Linux")

    copy_backend(DIST)
    copy_extras(DIST)
    if not args.skip_launcher:
        build_launcher(DIST)

    total = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())
    log(f"размер распакованного: {total / 1024 ** 2:.0f} МБ")
    log("(torch и модели — ещё около 4.5 ГБ — ставятся при первом запуске)")

    pack(DIST, version)

    print(f"\nГотово: {DIST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
