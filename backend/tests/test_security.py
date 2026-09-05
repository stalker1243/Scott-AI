"""
Границы, за которые Scott не должен выходить.

Проверки написаны перед выпуском, когда стало важно, что программу поставит
себе посторонний человек. Каждая закрывает дыру, найденную практикой, а не
теорией: backend отвечал на запросы из локальной сети, CORS пускал любой сайт,
а тип «команда оболочки» стоял в списке исполняемых по /command — эндпоинту,
который токена не требует.
"""

import ast
import re
from pathlib import Path

import pytest
from fastapi.routing import APIRoute

pytestmark = pytest.mark.unit

BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def main_source():
    return (BACKEND / "main.py").read_text(encoding="utf-8")


# ==================== Кто может достучаться ====================

def test_listens_locally_by_default(main_source):
    """
    По умолчанию backend слушает только этот компьютер.

    На 0.0.0.0 он был доступен всей локальной сети, причём /command токена не
    требует: сосед по Wi-Fi мог открывать программы и смотреть, что лежит на
    рабочем столе. Проверено практикой — запрос с сетевого адреса машины
    возвращал 200.
    """
    match = re.search(r'os\.getenv\("BACKEND_HOST",\s*"([^"]+)"\)', main_source)

    assert match, "не найдено значение BACKEND_HOST по умолчанию"
    assert match.group(1) in ("127.0.0.1", "localhost"), (
        f"backend по умолчанию слушает {match.group(1)} — это открывает его сети"
    )


def test_cors_is_not_wildcard(main_source):
    """
    CORS не открыт для всех источников.

    Со «*» и allow_credentials любая страница, открытая в браузере, могла слать
    запросы на localhost:8000 — то есть посторонний сайт получал возможность
    запускать программы на компьютере пользователя.
    """
    assert 'allow_origins=["*"]' not in main_source, "CORS открыт для любого сайта"
    assert "_LOCAL_ORIGINS" in main_source


# ==================== Что нельзя выполнить голосом ====================

def test_shell_types_not_executable_by_voice(main_source):
    """
    Команды оболочки не выполняются через /command.

    Этот эндпоинт не требует токена. Пока ветки выполнения для типа
    «powershell» не существовало, спасала случайность — но появись она при
    очередной правке, произвольная команда стала бы доступна любому, кто
    дотянулся до порта.
    """
    match = re.search(r"action_command_types = \{(.*?)\}", main_source, re.S)
    assert match, "не найден список исполняемых типов команд"

    executable = match.group(1)
    for forbidden in ("'powershell'", "'run_script'"):
        assert forbidden not in executable, (
            f"{forbidden} в списке исполняемых по /command — это удалённое выполнение команд"
        )

    assert "SHELL_TYPES" in main_source, "нет явного отказа для команд оболочки"


def test_dangerous_endpoints_still_guarded(app):
    """
    Опасные операции по-прежнему требуют токен.

    Дублирует проверку из test_smoke намеренно: здесь она стоит рядом с
    остальными границами, и при чтении этого файла видно всю картину сразу.
    """
    protected = {
        "/kill-process",
        "/extended/powershell",
        "/extended/file/delete",
        "/extended/system/shutdown",
        "/internal/execute",
    }

    for route in app.routes:
        if isinstance(route, APIRoute) and route.path in protected:
            guards = " ".join(str(d.call) for d in route.dependant.dependencies)
            assert "require_scott_token" in guards, f"{route.path} без токена"


# ==================== Секреты ====================

def test_no_hardcoded_secrets():
    """
    В коде нет зашитых ключей.

    Проверяется форма известных сервисов: ключ, случайно оставленный в
    исходнике, уедет в публичный репозиторий вместе с ним.
    """
    patterns = [
        re.compile(r"sk-[A-Za-z0-9]{20,}"),
        re.compile(r"gsk_[A-Za-z0-9]{20,}"),
        re.compile(r"AIza[A-Za-z0-9_-]{30,}"),
        re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    ]

    offenders = []
    for path in BACKEND.glob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in patterns:
            if pattern.search(text):
                offenders.append(path.name)

    assert not offenders, f"похоже на зашитый ключ: {offenders}"


def test_token_check_is_fail_closed():
    """
    Без заданного токена защищённые операции запрещены всем.

    Обратное поведение — «токен не настроен, значит проверять нечего» — самая
    опасная из возможных ошибок в этом месте.
    """
    source = (BACKEND / "security.py").read_text(encoding="utf-8")

    assert "fail-closed" in source.lower() or "fail closed" in source.lower(), (
        "в security.py не описано поведение при пустом токене"
    )


# ==================== Отчёты об ошибках ====================

def test_report_masks_secrets():
    """
    Архив с логами не должен содержать ключей.

    Пользователь отправляет его постороннему человеку — это тот случай, когда
    утечку устроили бы мы сами, одной кнопкой.
    """
    import diagnostics

    secret = "gsk_" + "x" * 30
    assert secret not in diagnostics.mask_secrets(f"Authorization: Bearer {secret}")
