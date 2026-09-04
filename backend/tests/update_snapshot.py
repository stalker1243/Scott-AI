"""
Пересобрать эталонный список маршрутов.

Запускать осознанно — после того, как эндпоинт добавлен или убран намеренно:

    cd backend && python tests/update_snapshot.py

Снимок нужен, чтобы перестановка кода по роутерам не меняла состав API
незаметно. Обновлять его «чтобы тест позеленел» бессмысленно: именно
расхождение и есть та новость, ради которой проверка существует.
"""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)
os.environ.setdefault("WARMUP_MODELS", "0")

from fastapi.routing import APIRoute  # noqa: E402

import main  # noqa: E402

rows = set()
for route in main.app.routes:
    if isinstance(route, APIRoute):
        for method in route.methods - {"HEAD", "OPTIONS"}:
            rows.add(f"{method} {route.path}")

snapshot = Path(__file__).parent / "routes_snapshot.txt"
snapshot.write_text("\n".join(sorted(rows)) + "\n", encoding="utf-8")
print(f"Снимок обновлён: {len(rows)} маршрутов -> {snapshot}")
