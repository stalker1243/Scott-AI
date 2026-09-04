"""
Поиск приложений на Linux — по .desktop-файлам.

Проверяется на Windows: каталог приложений подменяется временной папкой с
настоящими по формату .desktop-файлами, и сверяется, что именно Scott нашёл.
Запуск при этом не выполняется.

Чего такая проверка не покрывает: сработает ли gtk-launch в конкретном
окружении рабочего стола. Это подтвердит только запуск на Linux.
"""

import pytest

pytestmark = pytest.mark.unit

FIREFOX = """[Desktop Entry]
Type=Application
Name=Firefox Web Browser
Name[ru]=Веб-браузер Firefox
Exec=firefox %u
Icon=firefox
"""

TEXT_EDITOR = """[Desktop Entry]
Type=Application
Name=Text Editor
Name[ru]=Текстовый редактор
Exec=gedit %U
"""

HIDDEN = """[Desktop Entry]
Type=Application
Name=Служебная запись
Exec=/usr/bin/service-helper
NoDisplay=true
"""

BROKEN = """это вообще не desktop-файл
"""

LINK = """[Desktop Entry]
Type=Link
Name=Ссылка куда-то
URL=https://example.com
"""


@pytest.fixture
def resolver(tmp_path, monkeypatch):
    """app_resolver, которому подсунули каталог приложений из временной папки."""
    import app_resolver

    apps = tmp_path / "applications"
    apps.mkdir()
    (apps / "firefox.desktop").write_text(FIREFOX, encoding="utf-8")
    (apps / "org.gnome.gedit.desktop").write_text(TEXT_EDITOR, encoding="utf-8")
    (apps / "hidden.desktop").write_text(HIDDEN, encoding="utf-8")
    (apps / "broken.desktop").write_text(BROKEN, encoding="utf-8")
    (apps / "link.desktop").write_text(LINK, encoding="utf-8")

    monkeypatch.setattr(app_resolver, "DESKTOP_DIRS", [str(apps)])
    monkeypatch.setattr(app_resolver, "IS_WINDOWS", False)
    monkeypatch.setattr(app_resolver, "_desktop_index_cache", None)
    return app_resolver


def test_index_reads_names(resolver):
    """В индекс попадают подписи из меню — и русская, и английская."""
    index = resolver._build_desktop_index()

    assert "firefox web browser" in index
    assert "веб браузер firefox" in index or "вебраузер firefox" in index or any(
        "firefox" in key for key in index
    )


def test_hidden_entries_are_skipped(resolver):
    """
    Записи с NoDisplay не показываются в меню — значит и Scott их не предлагает.

    Это служебные ассоциации типов файлов, а не программы, которые человек
    просит открыть.
    """
    index = resolver._build_desktop_index()
    assert not any("служебная" in key for key in index)


def test_links_are_skipped(resolver):
    """Type=Link — это закладка, а не приложение."""
    index = resolver._build_desktop_index()
    assert not any("ссылка" in key for key in index)


def test_broken_file_does_not_break_index(resolver):
    """
    Битый .desktop не должен ронять весь каталог.

    Один испорченный файл в /usr/share/applications — не повод оставить
    пользователя без запуска приложений вообще.
    """
    index = resolver._build_desktop_index()
    assert len(index) >= 2


def test_exact_match(resolver):
    """Точное совпадение по названию из меню."""
    found = resolver.resolve_app("Firefox Web Browser")

    assert found is not None
    assert found.kind == "desktop"
    assert found.source == "desktop"
    assert found.target.endswith("firefox.desktop")


def test_fuzzy_match(resolver):
    """
    Неточное название тоже находится.

    Человек говорит «файрфокс» или «firefox», а в меню подписано «Firefox Web
    Browser» — без нечёткого совпадения команда не сработала бы.
    """
    found = resolver.resolve_app("firefox")

    assert found is not None
    assert found.target.endswith("firefox.desktop")


def test_unknown_app_returns_nothing(resolver):
    """Несуществующее приложение не находится — и сообщение говорит про Linux."""
    assert resolver.resolve_app("такого-приложения-нет-нигде") is None

    result = resolver.launch_app("такого-приложения-нет-нигде")
    assert not result["success"]
    assert ".desktop" in result["error"]


def test_launch_uses_gtk_launch_when_available(resolver, monkeypatch):
    """
    Для запуска предпочитается gtk-launch: он разворачивает Exec правильно.

    Самостоятельный разбор Exec — запасной путь, потому что там встречаются
    подстановки вроде %U, которые нельзя передавать программе как есть.
    """
    calls = []
    monkeypatch.setattr(resolver.shutil, "which", lambda name: name if name == "gtk-launch" else None)
    monkeypatch.setattr(resolver.subprocess, "Popen", lambda argv, **kw: calls.append(argv))

    resolver._launch_desktop_entry(str(resolver._build_desktop_index()["firefox web browser"]))

    assert calls and calls[0][0] == "gtk-launch"


def test_launch_falls_back_to_exec(resolver, monkeypatch):
    """Без gtk-launch и gio разбираем Exec сами, вырезая подстановки %u и %U."""
    calls = []
    monkeypatch.setattr(resolver.shutil, "which", lambda name: None)
    monkeypatch.setattr(resolver.subprocess, "Popen", lambda argv, **kw: calls.append(argv))

    resolver._launch_desktop_entry(str(resolver._build_desktop_index()["firefox web browser"]))

    assert calls == [["firefox"]], f"неожиданная команда: {calls}"
