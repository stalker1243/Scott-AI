"""
Защита от кода, который работает только на Windows.

Проект писался под Windows, и следы этого разбросаны по модулям: `os.startfile`
существует только там, `winreg` на Linux не импортируется вовсе. Одна такая
строка в достижимом месте — и на Linux падает не отдельная команда, а весь
модуль вместе с ней.

Проверки здесь статические: разбирается исходный код и сверяется, что каждый
Windows-только вызов стоит под проверкой системы. Так они ловят проблему на
Windows, где протестировать Linux иначе невозможно.
"""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

BACKEND = Path(__file__).resolve().parent.parent

# Модули, которые обязаны импортироваться на любой системе.
CORE_MODULES = [
    "os_actions.py",
    "app_resolver.py",
    "command_executor.py",
    "command_executor_extended.py",
    "file_system_manager.py",
    "system_monitor.py",
    "device_settings.py",
    "diagnostics.py",
    "silero_tts.py",
]

WINDOWS_ONLY_CALLS = {"startfile"}
WINDOWS_ONLY_IMPORTS = {"winreg", "msvcrt", "winsound"}


def source_of(name: str) -> str:
    return (BACKEND / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("module", CORE_MODULES)
def test_no_unconditional_windows_import(module):
    """
    winreg не импортируется на верхнем уровне.

    Такой импорт роняет модуль целиком при загрузке на Linux — не команду, не
    функцию, а всё сразу. В app_resolver это уже случалось: из-за одной строки
    запуск приложений был недоступен полностью.
    """
    tree = ast.parse(source_of(module))

    for node in tree.body:  # именно верхний уровень, вложенные — нормально
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in WINDOWS_ONLY_IMPORTS, (
                    f"{module}: безусловный импорт {alias.name} — модуль не загрузится на Linux"
                )


@pytest.mark.parametrize("module", CORE_MODULES)
def test_startfile_is_guarded(module):
    """
    Каждый os.startfile защищён проверкой системы.

    Проверка грубая — ищем упоминание платформы в той же функции, — но она
    ловит именно то, ради чего заведена: вызов, до которого на Linux можно
    добраться и получить AttributeError вместо работы.
    """
    tree = ast.parse(source_of(module))

    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        calls_startfile = any(
            isinstance(node, ast.Attribute) and node.attr in WINDOWS_ONLY_CALLS
            for node in ast.walk(func)
        )
        if not calls_startfile:
            continue

        body = ast.dump(func)
        guarded = any(marker in body for marker in ("platform", "IS_WINDOWS", "is_windows", "'nt'", "\"nt\""))
        assert guarded, f"{module}.{func.name}: os.startfile без проверки системы"


def test_os_actions_covers_three_systems():
    """
    Слой действий знает про Windows, Linux и macOS.

    Не формальность: пропущенная ветка означает, что на этой системе команда
    молча не работает — а «молча» здесь худшее слово.
    """
    import os_actions

    for name in (actions := ["volume_command", "brightness_command", "power_command"]):
        assert hasattr(os_actions, name)

    source = source_of("os_actions.py")
    for marker in ("WINDOWS", "LINUX", "MACOS"):
        assert marker in source


def test_no_sudo_in_backend():
    """
    Нигде не вызывается sudo.

    Пароль в фоновом процессе ввести некому: команда повиснет до таймаута, а
    пользователь решит, что Scott сломался. Права на выключение и перезагрузку
    даёт polkit через systemctl.
    """
    offenders = []
    for path in BACKEND.glob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "sudo " in stripped and "sudo" not in stripped.split("#")[0].split('"""')[0][:0]:
                if '"sudo' in stripped or "'sudo" in stripped or "sudo shutdown" in stripped:
                    offenders.append(f"{path.name}:{number}")

    assert not offenders, f"вызов sudo: {offenders}"
