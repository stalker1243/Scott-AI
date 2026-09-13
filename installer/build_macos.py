"""
Сборка Scott AI для macOS.

Отличие от других систем не в командах, а в том, что программа на macOS — это
не файл, а папка со строгим устройством:

    ScottAI.app/Contents/
        Info.plist          описание: имя, версия, значок, запрашиваемые права
        MacOS/ScottAI       исполняемый файл — и только он
        Resources/          всё остальное: значок, backend, сопроводительное

Положить backend рядом с исполняемым файлом нельзя: подпись бандла считает
посторонние файлы в MacOS/ нарушением, и система откажется запускать программу.
Лаунчер знает про это и ищет backend ещё и в Resources.

ПРАВА. Микрофон и управление другими программами на macOS спрашиваются у
человека, и спрашиваются ОДИН раз — по тексту из Info.plist. Без строки
NSMicrophoneUsageDescription система не покажет запрос вовсе, а просто убьёт
процесс при первом обращении к микрофону; без NSAppleEventsUsageDescription
молча перестанут работать громкость, яркость и выключение — они идут через
osascript.

ПОДПИСИ НЕТ. Для неё нужен платный счёт разработчика Apple. Скачанный бандл
macOS пометит карантином и откажется открывать со словами «повреждён» — это не
про повреждение, а про отсутствие подписи. Снимается одной командой, и она
написана в сопроводительном файле рядом.

Запуск:

    python installer/build_macos.py                   # обе архитектуры
    python installer/build_macos.py --arch arm64      # только процессоры Apple
    python installer/build_macos.py --clean
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "installer"
DIST = INSTALLER / "dist-macos"
RELEASE = INSTALLER / "release"

BUNDLE_ID = "com.scottai.launcher"

# Самая старая macOS, на которой это заработает. Big Sur — первая с
# процессорами Apple; поддерживать более ранние смысла нет, .NET 10 их и сам
# не поддерживает.
MIN_MACOS = "11.0"

# Что из backend попадает в бандл. Перечислено явно: рядом лежат логи, кэш и
# данные конкретной машины, которым на чужом компьютере делать нечего.
BACKEND_FILES = ["*.py", "requirements.txt", "pytest.ini"]

ARCHES = {
    "arm64": "osx-arm64",      # процессоры Apple, с 2020 года
    "x86_64": "osx-x64",       # прежние Mac на Intel
}


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


# ==================== Значок ====================

def build_icns(target: Path) -> bool:
    """
    Собрать значок macOS из готовых PNG.

    Формат .icns несложен: заголовок с общей длиной, затем куски, каждый со
    своим четырёхбуквенным именем — оно и задаёт размер. Собирается вручную
    потому, что штатный iconutil есть только на Mac, а сборка идёт и с
    Windows.

    Куски мельче 128 точек намеренно пропущены: в них полагается формат,
    который так просто не собрать, а система сама уменьшит большой значок.
    """
    исходники = {
        "ic07": ROOT / "ScottAI_avalonia" / "Assets" / "icon-128.png",
        "ic08": ROOT / "ScottAI_avalonia" / "Assets" / "icon-256.png",
    }

    куски = []
    for имя, путь in исходники.items():
        if not путь.exists():
            continue
        данные = путь.read_bytes()
        куски.append(имя.encode("ascii") + struct.pack(">I", len(данные) + 8) + данные)

    if not куски:
        log("значков не нашлось — бандл будет с системным")
        return False

    тело = b"".join(куски)
    target.write_bytes(b"icns" + struct.pack(">I", len(тело) + 8) + тело)
    log(f"значок собран: {target.name}")
    return True


# ==================== Описание бандла ====================

def write_info_plist(contents: Path, version: str, есть_значок: bool) -> None:
    """
    Описание бандла.

    Тексты про права человек увидит в системном запросе — их пишем по-русски и
    по существу: «программе нужен доступ» ничего не объясняет, а «Scott слышит
    обращение по имени» отвечает на вопрос, который в этот момент возникает.
    """
    описание = {
        "CFBundleName": "ScottAI",
        "CFBundleDisplayName": "Scott AI",
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleExecutable": "ScottAI",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "LSMinimumSystemVersion": MIN_MACOS,

        # Без этого окно рисуется в четыре раза крупнее и мутно: система
        # считает программу не умеющей работать с экранами Retina.
        "NSHighResolutionCapable": True,

        "NSMicrophoneUsageDescription":
            "Scott слушает обращение по имени и выполняет голосовые команды.",
        "NSAppleEventsUsageDescription":
            "Scott меняет громкость и яркость, открывает программы и "
            "выключает компьютер по вашей просьбе.",
    }

    if есть_значок:
        описание["CFBundleIconFile"] = "scott.icns"

    (contents / "Info.plist").write_bytes(plistlib.dumps(описание))
    log("Info.plist записан")


# ==================== Сборка ====================

def build_launcher(macos_dir: Path, runtime: str) -> None:
    """
    Собрать лаунчер под выбранную архитектуру.

    self-contained: .NET на машине человека не нужен, всё внутри. Плюс к
    размеру около семидесяти мегабайт, зато не приходится объяснять, как
    ставить среду выполнения.
    """
    project = ROOT / "ScottAI_avalonia" / "ScottAI.Avalonia.csproj"

    log(f"собираю лаунчер под {runtime} (это займёт минуту)…")
    subprocess.run(
        [
            "dotnet", "publish", str(project),
            "-c", "Release",
            "-r", runtime,
            "--self-contained", "true",
            "-o", str(macos_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    # Отладочные символы в дистрибутиве не нужны — это десятки мегабайт.
    for pdb in macos_dir.glob("*.pdb"):
        pdb.unlink()

    исполняемый = macos_dir / "ScottAI"
    if исполняемый.exists():
        исполняемый.chmod(0o755)

    log("лаунчер собран")


def copy_backend(resources: Path) -> None:
    source = ROOT / "backend"
    target = resources / "backend"
    target.mkdir(parents=True, exist_ok=True)

    count = 0
    for pattern in BACKEND_FILES:
        for item in source.glob(pattern):
            if item.is_file():
                shutil.copy2(item, target / item.name)
                count += 1

    log(f"backend скопирован: {count} файлов")


def copy_extras(resources: Path) -> None:
    for name in (".env.example", "README.md", "VERSION.json"):
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, resources / name)


README = """Scott AI {version} для macOS

УСТАНОВКА

  1. Перетащите ScottAI.app в папку «Программы».

  2. При первом запуске macOS скажет, что программа «повреждена и не может
     быть открыта». Это не повреждение: у сборки нет подписи Apple, для
     которой нужен платный счёт разработчика. Снимается одной командой в
     Терминале:

         xattr -dr com.apple.quarantine /Applications/ScottAI.app

  3. Нужен Python 3.13 — Scott считает речь им. Если его нет:

         brew install python@3.13

     Библиотеки Scott поставит сам при первом запуске.

ЧТО СПРОСИТ СИСТЕМА

  Доступ к микрофону — чтобы слышать обращение по имени.
  Управление программами — чтобы менять громкость и открывать приложения.

  Если отказать, Scott продолжит работать, но молча и без рук: команды
  голосом приниматься не будут.

ЧТО РАБОТАЕТ ИНАЧЕ, ЧЕМ НА WINDOWS

  Распознавание речи считает процессор: библиотека, которая этим занимается,
  графику Apple не поддерживает. Синтез — наоборот, работает на Metal.
"""


def write_readme(dest: Path, version: str) -> None:
    """
    Что человек прочитает рядом с программой.

    Главное здесь — про карантин. Без подписи Apple система говорит
    «повреждён», и это сообщение сбивает с толку больше всего: файл цел,
    просто не подписан.
    """
    (dest / "ПРОЧТИТЕ.txt").write_text(README.format(version=version), encoding="utf-8")


def build_bundle(dest: Path, version: str, runtime: str, skip_launcher: bool) -> Path:
    """Собрать ScottAI.app целиком."""
    bundle = dest / "ScottAI.app"
    if bundle.exists():
        shutil.rmtree(bundle)

    contents = bundle / "Contents"
    macos_dir = contents / "MacOS"
    resources = contents / "Resources"

    macos_dir.mkdir(parents=True)
    resources.mkdir(parents=True)

    if skip_launcher:
        # Заглушка вместо программы: проверять устройство бандла можно и без
        # минутной сборки.
        (macos_dir / "ScottAI").write_text("", encoding="utf-8")
    else:
        build_launcher(macos_dir, runtime)

    есть_значок = build_icns(resources / "scott.icns")
    write_info_plist(contents, version, есть_значок)

    copy_backend(resources)
    copy_extras(resources)

    return bundle


def pack(dest: Path, version: str, arch: str) -> Path:
    """
    Упаковать готовый бандл.

    На Mac — в образ диска: это привычный там способ раздавать программы, и
    окно с перетаскиванием в «Программы» человеку знакомо. На других системах
    hdiutil взять неоткуда, поэтому архив — с явной простановкой прав на
    исполнение: на Windows их нет как понятия, и без этого распакованный
    лаунчер не запустился бы.
    """
    RELEASE.mkdir(parents=True, exist_ok=True)
    имя = f"ScottAI-{version}-macos-{arch}"

    if sys.platform == "darwin" and shutil.which("hdiutil"):
        образ = RELEASE / f"{имя}.dmg"
        if образ.exists():
            образ.unlink()

        log("собираю образ диска…")
        subprocess.run(
            ["hdiutil", "create", "-volname", f"Scott AI {version}",
             "-srcfolder", str(dest), "-ov", "-format", "UDZO", str(образ)],
            check=True, capture_output=True, text=True,
        )
        размер = образ.stat().st_size / 1024 ** 2
        log(f"образ готов: {образ} ({размер:.0f} МБ)")
        return образ

    архив = RELEASE / f"{имя}.zip"
    if архив.exists():
        архив.unlink()

    log("упаковываю архив…")
    with zipfile.ZipFile(архив, "w", zipfile.ZIP_DEFLATED) as z:
        for файл in sorted(dest.rglob("*")):
            if not файл.is_file():
                continue

            внутри = файл.relative_to(dest)
            запись = zipfile.ZipInfo(str(внутри).replace(os.sep, "/"))
            запись.compress_type = zipfile.ZIP_DEFLATED

            # Права хранятся в верхней половине external_attr. Исполняемый
            # файл и библиотеки должны остаться исполняемыми, иначе на Mac
            # распакованный бандл просто не запустится.
            #
            # Именно они, а не всё подряд в MacOS/: рядом лежат сборки .NET,
            # которые никто не запускает напрямую, и раздавать им право на
            # исполнение незачем.
            исполняемый = (файл.name in ("ScottAI", "createdump")
                           or файл.suffix in (".dylib", ".so"))
            запись.external_attr = (0o755 if исполняемый else 0o644) << 16

            z.writestr(запись, файл.read_bytes())

    размер = архив.stat().st_size / 1024 ** 2
    log(f"архив готов: {архив} ({размер:.0f} МБ)")
    return архив


def main() -> int:
    parser = argparse.ArgumentParser(description="Собрать Scott AI для macOS")
    parser.add_argument("--clean", action="store_true", help="очистить папку сборки перед началом")
    parser.add_argument("--arch", choices=sorted(ARCHES), action="append",
                        help="какую архитектуру собирать (по умолчанию обе)")
    parser.add_argument("--skip-launcher", action="store_true",
                        help="не собирать лаунчер (быстрая проверка устройства бандла)")
    args = parser.parse_args()

    if args.clean and DIST.exists():
        shutil.rmtree(DIST)
        log("папка сборки очищена")

    version = read_version()
    архитектуры = args.arch or sorted(ARCHES)

    print(f"Собираю Scott AI {version} для macOS: {', '.join(архитектуры)}")

    for arch in архитектуры:
        папка = DIST / arch
        папка.mkdir(parents=True, exist_ok=True)

        print(f"\n[{arch}]")
        бандл = build_bundle(папка, version, ARCHES[arch], args.skip_launcher)
        write_readme(папка, version)

        размер = sum(f.stat().st_size for f in бандл.rglob("*") if f.is_file())
        log(f"размер бандла: {размер / 1024 ** 2:.0f} МБ")

        pack(папка, version, arch)

    print(f"\nГотово: {DIST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
