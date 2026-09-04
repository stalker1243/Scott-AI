"""
Общая подготовка для тестов.

Backend запускается из своей папки (`cd backend && python main.py`), и пути
внутри него относительные — `data/profiles.json` и прочее. Тесты обязаны
работать в тех же условиях, иначе менеджеры не найдут свои файлы, поэтому
рабочая директория подменяется на backend, а сама папка добавляется в
sys.path: модули там импортируют друг друга по короткому имени.
"""

import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.chdir(BACKEND_DIR)

# Прогрев моделей при импорте не нужен: он занимает GPU на несколько секунд и
# к предмету проверок отношения не имеет. Выключается той же переменной, что и
# в бою.
os.environ.setdefault("WARMUP_MODELS", "0")


@pytest.fixture(scope="session")
def main_module():
    """
    Импортированный main.py.

    Импорт стоит около трёх секунд (поднимаются профиль, база знаний, голос),
    поэтому делается один раз на весь прогон. Сам факт успешного импорта уже
    показателен: именно здесь ловятся обрывы файла и потерянные блоки.
    """
    import main

    return main


@pytest.fixture(scope="session")
def app(main_module):
    return main_module.app


@pytest.fixture(scope="session")
def main_source():
    """Исходный текст main.py — для проверок, которым хватает разбора кода."""
    return (BACKEND_DIR / "main.py").read_text(encoding="utf-8")
