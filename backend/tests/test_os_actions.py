"""
Выбор системных команд на всех трёх платформах.

Особенность этих проверок: они выполняются на Windows, но проверяют и Linux, и
macOS — подменяются `platform.system()` и набор установленных инструментов, а
сверяется то, ЧТО именно Scott собирается запустить. Сами команды при этом не
выполняются.

Так можно поймать почти всё, кроме одного: действительно ли выбранная команда
меняет громкость в конкретном дистрибутиве. Это проверяется только запуском
там, и такой проверки у этого кода пока не было.

Почему кандидатов несколько: на Linux звуком заведует то PipeWire, то
PulseAudio, то голый ALSA, и единственной верной команды не существует.
Прежний код звал `amixer` всегда — на системе с PipeWire он тихо не делает
ничего.
"""

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def actions():
    import os_actions

    return os_actions


def force_os(actions, monkeypatch, name):
    monkeypatch.setattr(actions.platform, "system", lambda: name)


def only_tools(actions, monkeypatch, *available):
    """Сделать вид, что в системе установлены только перечисленные программы."""
    monkeypatch.setattr(actions.shutil, "which", lambda name: name if name in available else None)


# ==================== Громкость ====================

@pytest.mark.parametrize("tools,expected_tool", [
    (("wpctl", "pactl", "amixer"), "wpctl"),   # PipeWire — самый частый сегодня
    (("pactl", "amixer"), "pactl"),            # PulseAudio
    (("amixer",), "amixer"),                   # голый ALSA
])
def test_linux_volume_picks_available_tool(actions, monkeypatch, tools, expected_tool):
    """Берётся первый доступный инструмент, а не один жёстко зашитый."""
    force_os(actions, monkeypatch, actions.LINUX)
    only_tools(actions, monkeypatch, *tools)

    command = actions.volume_command("up")

    assert command is not None
    assert command[0] == expected_tool


def test_linux_volume_without_tools_is_honest(actions, monkeypatch):
    """
    Без единого инструмента команда не выдумывается.

    Прежний код в этом случае звал amixer и рапортовал об успехе, хотя громкость
    не менялась. Молчаливая ложь хуже отказа: пользователь решит, что сломан
    звук, а не что не хватает пакета.
    """
    force_os(actions, monkeypatch, actions.LINUX)
    only_tools(actions, monkeypatch)

    assert actions.volume_command("up") is None

    result = actions.change_volume("up")
    assert not result["success"]
    assert "wpctl" in result["error"]


def test_volume_direction_differs(actions, monkeypatch):
    """Прибавить и убавить — разные команды (звучит очевидно, но легко перепутать)."""
    force_os(actions, monkeypatch, actions.LINUX)
    only_tools(actions, monkeypatch, "wpctl")

    assert actions.volume_command("up") != actions.volume_command("down")
    assert "5%+" in actions.volume_command("up")
    assert "5%-" in actions.volume_command("down")


def test_windows_volume_uses_media_key(actions, monkeypatch):
    """На Windows без nircmd шлём мультимедийную клавишу — её понимает сама система."""
    force_os(actions, monkeypatch, actions.WINDOWS)
    only_tools(actions, monkeypatch)

    command = actions.volume_command("up")

    assert command[0] == "powershell"
    assert "175" in " ".join(command)


def test_macos_volume_uses_osascript(actions, monkeypatch):
    force_os(actions, monkeypatch, actions.MACOS)
    only_tools(actions, monkeypatch)

    assert actions.volume_command("up")[0] == "osascript"


# ==================== Яркость ====================

@pytest.mark.parametrize("tools,expected", [
    (("brightnessctl", "light"), "brightnessctl"),
    (("light",), "light"),
])
def test_linux_brightness_picks_available_tool(actions, monkeypatch, tools, expected):
    force_os(actions, monkeypatch, actions.LINUX)
    only_tools(actions, monkeypatch, *tools)

    assert actions.brightness_command("up")[0] == expected


def test_linux_brightness_without_tools_is_honest(actions, monkeypatch):
    """Яркостью на Linux без brightnessctl управлять нечем — так и говорим."""
    force_os(actions, monkeypatch, actions.LINUX)
    only_tools(actions, monkeypatch)

    result = actions.change_brightness("up")
    assert not result["success"]
    assert "brightnessctl" in result["error"]


# ==================== Питание ====================

def test_linux_power_prefers_systemctl(actions, monkeypatch):
    """
    Питанием заведует systemctl, а не sudo.

    Это принципиально: `sudo shutdown` в фоновом процессе просто повис бы,
    ожидая пароль, которого никто не увидит. systemctl спрашивает разрешение
    через polkit, и в обычной сессии выключение разрешено без пароля.
    """
    force_os(actions, monkeypatch, actions.LINUX)
    only_tools(actions, monkeypatch, "systemctl")

    assert actions.power_command("shutdown") == ["systemctl", "poweroff"]
    assert actions.power_command("restart") == ["systemctl", "reboot"]
    assert actions.power_command("sleep") == ["systemctl", "suspend"]


def test_linux_power_without_systemd(actions, monkeypatch):
    """На системе без systemd остаётся shutdown с задержкой."""
    force_os(actions, monkeypatch, actions.LINUX)
    only_tools(actions, monkeypatch)

    assert actions.power_command("shutdown")[0] == "shutdown"


def test_no_sudo_anywhere(actions, monkeypatch):
    """
    Ни одна команда не начинается с sudo.

    Пароль в фоновом процессе ввести некому: команда повиснет до таймаута, а
    пользователь увидит «ничего не произошло».
    """
    force_os(actions, monkeypatch, actions.LINUX)
    only_tools(actions, monkeypatch, "systemctl", "wpctl", "brightnessctl", "xdg-open")

    commands = [
        actions.volume_command("up"),
        actions.brightness_command("up"),
        actions.power_command("shutdown"),
        actions.power_command("restart"),
        actions.power_command("sleep"),
    ]
    for command in commands:
        assert command and command[0] != "sudo", f"sudo в команде: {command}"


# ==================== Оболочка ====================

def test_shell_differs_by_os(actions, monkeypatch):
    """PowerShell на Windows, bash на остальных."""
    force_os(actions, monkeypatch, actions.WINDOWS)
    assert actions.shell_command("echo привет")[0] == "powershell"

    force_os(actions, monkeypatch, actions.LINUX)
    assert actions.shell_command("echo привет")[0] == "/bin/bash"


def test_capabilities_report_missing_tools(actions, monkeypatch):
    """
    Диагностика честно показывает, чего на машине нет.

    На Linux без brightnessctl яркость не изменить вовсе — лучше сказать прямо,
    чем молча ничего не делать.
    """
    force_os(actions, monkeypatch, actions.LINUX)
    only_tools(actions, monkeypatch, "pactl")

    caps = actions.describe_capabilities()

    assert caps["os"] == actions.LINUX
    assert caps["громкость"] is True
    assert caps["яркость"] is False
