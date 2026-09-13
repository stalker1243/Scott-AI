"""
Поиск и запуск приложений на macOS.

До этого на Mac Scott искал .desktop-файлы — описания программ, которых там не
бывает вовсе. Ветка «не Windows» означала «Linux», и «открой Safari» на Mac не
нашло бы ничего и никогда.

Проверки идут с подменой платформы и каталогов: настоящий Mac для них не нужен,
а нужен он будет для другого — подтвердить, что `open` действительно поднимает
программу, и что Spotlight отвечает так, как написано в документации.
"""

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

try:
    import app_resolver
except ImportError:  # pragma: no cover — запуск из корня репозитория
    from backend import app_resolver


def бандл(корень: Path, имя: str, показывать_как: str = "") -> Path:
    """
    Приложение macOS — папка с суффиксом .app и описанием внутри.

    Делается настоящей папкой, а не заглушкой: каталог строится обходом
    файловой системы, и подделка проверяла бы не его.
    """
    путь = корень / f"{имя}.app"
    (путь / "Contents").mkdir(parents=True, exist_ok=True)

    описание = """<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>{имя}</string>
{показ}</dict>
</plist>
"""
    показ = ""
    if показывать_как:
        показ = f"    <key>CFBundleDisplayName</key>\n    <string>{показывать_как}</string>\n"

    (путь / "Contents" / "Info.plist").write_text(
        описание.format(имя=имя, показ=показ), encoding="utf-8")
    return путь


@pytest.fixture
def mac(monkeypatch, tmp_path):
    """Система, которая считает себя macOS, с приложениями во временной папке."""
    приложения = tmp_path / "Applications"
    приложения.mkdir()

    monkeypatch.setattr(app_resolver, "IS_MACOS", True)
    monkeypatch.setattr(app_resolver, "IS_WINDOWS", False)
    monkeypatch.setattr(app_resolver, "MAC_APP_DIRS", [str(приложения)])
    monkeypatch.setattr(app_resolver, "_bundle_index_cache", None)

    # Spotlight в проверках не участвует: он отвечает за то, что лежит вне
    # обычных папок, и его ответ здесь только скрыл бы дыры в каталоге.
    monkeypatch.setattr(app_resolver, "_spotlight_lookup", lambda name: None)

    yield приложения

    monkeypatch.setattr(app_resolver, "_bundle_index_cache", None)


# ==================== Каталог ====================

def test_приложение_находится_по_имени_папки(mac):
    бандл(mac, "Safari")

    найдено = app_resolver.resolve_app("safari")

    assert найдено is not None, "Safari не нашлась в /Applications"
    assert найдено.target.endswith("Safari.app")
    assert найдено.kind == "bundle"


def test_приложение_находится_по_подписи_из_описания(mac):
    """
    Человек называет программу так, как она подписана у него на экране.

    На локализованной системе подпись и имя папки расходятся: папка
    Preview.app, а в меню — «Просмотр». По имени папки такое не найти.
    """
    бандл(mac, "Preview", показывать_как="Просмотр")

    assert app_resolver.resolve_app("просмотр") is not None


def test_программы_внутри_подпапок_тоже_видны(mac):
    """Adobe, Microsoft и прочие складывают свои программы в отдельную папку."""
    подпапка = mac / "Microsoft Office"
    подпапка.mkdir()
    бандл(подпапка, "Microsoft Word")

    assert app_resolver.resolve_app("microsoft word") is not None


def test_служебные_программы_внутри_бандла_не_попадают_в_каталог(mac):
    """
    Внутри каждого приложения лежат свои вспомогательные бандлы — обновление,
    отчёты о сбоях. Человек их не знает и не просит, а в нечётком поиске они
    перетягивали бы на себя чужие запросы.
    """
    safari = бандл(mac, "Safari")
    внутренний = safari / "Contents" / "Library" / "Helpers"
    внутренний.mkdir(parents=True)
    бандл(внутренний, "Safari Crash Reporter")

    каталог = app_resolver._build_bundle_index()

    assert "safari" in каталог
    assert not any("crash" in ключ for ключ in каталог), (
        f"служебные бандлы попали в каталог: {sorted(каталог)}")


def test_приблизительное_имя_тоже_срабатывает(mac):
    """«Открой хром» — а программа подписана Google Chrome."""
    бандл(mac, "Google Chrome")

    найдено = app_resolver.resolve_app("google chrom")

    assert найдено is not None
    assert найдено.target.endswith("Google Chrome.app")


# ==================== Запуск ====================

def test_запуск_идёт_через_open(mac, monkeypatch):
    """
    Приложение поднимается командой open, а не исполняемым файлом внутри бандла.

    Прямой запуск даёт процесс без значка в Dock, без прав и без окружения —
    часть программ так попросту не работает.
    """
    бандл(mac, "Safari")

    запущено = {}

    def перехват(argv, **kwargs):
        запущено["argv"] = argv
        return None

    monkeypatch.setattr(subprocess, "Popen", перехват)

    результат = app_resolver.launch_app("safari")

    assert результат["success"], результат.get("error")
    assert запущено["argv"][0] == "open", f"запускали не через open: {запущено['argv']}"
    assert запущено["argv"][1].endswith("Safari.app")


def test_о_ненайденном_говорится_по_месту(mac):
    """
    Перечислять человеку на Mac каталоги Linux бессмысленно: он пойдёт их
    искать и не найдёт.
    """
    ответ = app_resolver.launch_app("несуществующая программа")

    assert not ответ["success"]
    assert ".desktop" not in ответ["error"]
    assert "Applications" in ответ["error"]


def test_каталог_пересобирается_под_свою_систему(mac):
    бандл(mac, "Safari")

    итог = app_resolver.refresh_index()

    # Не «startapps» и не «desktop»: на Mac их строить не из чего, и попытка
    # вернула бы ноль там, где программа есть.
    assert итог == {"applications": 1}, f"пересборка вернула не то: {итог}"
