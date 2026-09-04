"""
Проверки, которые ловят поломки от неаккуратной правки main.py.

Набор не случайный: каждый тест здесь соответствует тому, что в проекте уже
ломалось или ломалось бы незаметно. Ни один не требует запущенного backend —
достаточно импорта, поэтому весь файл проходит за несколько секунд.
"""

import ast
from pathlib import Path

import pytest
from fastapi.routing import APIRoute

pytestmark = pytest.mark.smoke

SNAPSHOT = Path(__file__).parent / "routes_snapshot.txt"


def collect_routes(app):
    """Маршруты приложения в виде «МЕТОД путь», без служебных /docs и /openapi.json."""
    rows = set()
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods - {"HEAD", "OPTIONS"}:
                rows.add(f"{method} {route.path}")
    return rows


# ==================== Целостность самого файла ====================

def test_main_imports(main_module):
    """
    main.py импортируется целиком.

    Звучит тривиально, но именно это ловит обрыв файла: при автоматическом
    удалении блоков из него однажды уехал кусок кода, и модуль перестал быть
    рабочим, хотя внешне выглядел нормально.
    """
    assert main_module.app is not None


def test_entrypoint_present(main_source):
    """
    Блок `if __name__ == "__main__"` с запуском uvicorn на месте.

    Реальный случай: автоматическая чистка «пустых» секций унесла этот блок
    целиком. Backend после этого стартовал, печатал приветствие, доходил до
    конца файла и молча завершался, не открыв порт, — а по логам всё выглядело
    штатно.
    """
    tree = ast.parse(main_source)
    entrypoints = [
        node for node in tree.body
        if isinstance(node, ast.If)
        and any(isinstance(n, ast.Name) and n.id == "__name__" for n in ast.walk(node.test))
    ]
    assert entrypoints, "Потерян блок if __name__ == '__main__' — backend не откроет порт"
    # Сравнение выносится в переменную, иначе pytest вываливает в отчёт весь
    # исходник main.py целиком — и настоящее сообщение в нём теряется.
    starts_server = "uvicorn.run" in main_source
    assert starts_server, "В точке входа нет запуска uvicorn"


def test_error_handling_configured(main_source):
    """
    Логирование и перехват необработанных исключений настроены.

    Тот же случай, что и выше: вместе с секцией однажды уехала настройка
    logging и sys.excepthook. Backend продолжал работать, но падения переставали
    попадать в backend_errors.log — то есть терялась именно та информация,
    ради которой всё это заводилось.
    """
    missing = [n for n in ("logging.basicConfig", "sys.excepthook", "set_exception_handler")
               if n not in main_source]
    assert not missing, f"Потеряны настройки обработки ошибок: {missing}"


def test_model_warmup_wired(main_source):
    """
    Прогрев моделей подключён к старту.

    Без него первая голосовая команда после запуска стоит около семи секунд
    вместо одной: Whisper и Silero грузятся лениво. Потерять этот вызов при
    правке lifespan легко, а заметить — только на слух и не сразу.
    """
    defined = "_warmup_models" in main_source
    scheduled = "create_task(_warmup_models())" in main_source
    assert defined, "Функция прогрева моделей пропала"
    assert scheduled, "Прогрев не запускается при старте"


# ==================== Состав API ====================

def test_routes_match_snapshot(app):
    """
    Список маршрутов совпадает с эталонным снимком.

    Главная страховка при переносе эндпоинтов в роутеры: перестановка кода не
    должна ни терять существующие пути, ни добавлять новые. Если эндпоинт
    добавлен или удалён намеренно — обновите снимок:

        python tests/update_snapshot.py
    """
    current = collect_routes(app)
    expected = {line.strip() for line in SNAPSHOT.read_text(encoding="utf-8").splitlines() if line.strip()}

    missing = sorted(expected - current)
    added = sorted(current - expected)
    assert not missing, f"Пропали маршруты: {missing}"
    assert not added, f"Появились новые маршруты (обновите снимок, если так и задумано): {added}"


def test_no_duplicate_routes(app):
    """
    Один путь обслуживает ровно один обработчик.

    В проекте уже было двадцать семь эндпоинтов, объявленных дважды: в роутере
    и заново ниже по main.py. FastAPI отдаёт запрос первому совпавшему, поэтому
    вторые не выполнялись никогда — при этом правки в них выглядели рабочими.
    Ошибка тихая, и найти её без такой проверки трудно.
    """
    seen, duplicates = set(), []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods - {"HEAD", "OPTIONS"}:
            key = f"{method} {route.path}"
            if key in seen:
                duplicates.append(key)
            seen.add(key)
    assert not duplicates, f"Дублирующиеся (недостижимые) маршруты: {sorted(set(duplicates))}"


@pytest.mark.parametrize("route", [
    "GET /health",
    "POST /command",
    "POST /ask",
    "POST /speech_to_text",
    "POST /text_to_speech",
    "POST /speak",
    "GET /voice/available",
    "POST /voice/select",
    "GET /profiles/list",
    "GET /macros/list",
    "POST /extended/powershell",
    "GET /ai/status",
    "GET /analytics/comprehensive",
    "GET /timings",
])
def test_key_route_present(app, route):
    """Ключевые маршруты на месте — по одному, чтобы сразу было видно, какой пропал."""
    assert route in collect_routes(app)


# ==================== Безопасность ====================

DANGEROUS = [
    "POST /kill-process",
    "POST /extended/powershell",
    "POST /extended/file/delete",
    "POST /extended/system/shutdown",
    "POST /extended/system/restart",
    "POST /extended/system/sleep",
]


@pytest.mark.parametrize("route", DANGEROUS)
def test_dangerous_route_requires_token(app, route):
    """
    Опасные операции закрыты токеном.

    Проверка на будущее: при переносе эндпоинта в новый роутер зависимость
    require_scott_token легко не взять с собой, и выключение компьютера или
    выполнение PowerShell окажется доступным без всякой проверки. Внешне
    эндпоинт при этом работает даже лучше — просто отвечает всем.
    """
    method, path = route.split(" ", 1)
    target = next(
        (r for r in app.routes
         if isinstance(r, APIRoute) and r.path == path and method in r.methods),
        None,
    )
    assert target is not None, f"Маршрут {route} исчез"

    guards = " ".join(str(d.call) for d in target.dependant.dependencies)
    assert "require_scott_token" in guards, f"{route} остался без проверки токена"
    assert "check_rate_limit" in guards, f"{route} остался без ограничителя частоты"
