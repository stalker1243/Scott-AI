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
import importlib
from functools import lru_cache
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
os.environ['SCOTT_SEMANTIC_MEMORY'] = '0'  # Unit tests never download or run real embedding models.


@pytest.fixture(autouse=True)
def без_чужой_персонализации(tmp_path, monkeypatch):
    """
    Персонализация — всегда пустая, какой бы она ни была на этой машине.

    Настройки характера и рассказ о себе подмешиваются к указанию модели в
    каждом запросе. Значит любая проверка, сравнивающая отправленное указание с
    ожидаемым, начинает зависеть от того, что разработчик настроил себе в
    лаунчере. Так и случилось: два теста ИИ-провайдеров позеленели у одного и
    покраснели у другого, хотя код был один и тот же.
    """
    try:
        import personality
    except ImportError:  # pragma: no cover — запуск из корня репозитория
        from backend import personality

    monkeypatch.setattr(personality, "CONFIG_PATH", tmp_path / "personality.json")


@pytest.fixture(autouse=True)
def isolated_conversation_file(tmp_path, tmp_path_factory, monkeypatch):
    # Both spellings are used by the app/tests. They can be distinct modules
    # with distinct singletons; isolate each instead of only the flat import.
    for name in ('intelligent_answerer', 'backend.intelligent_answerer'):
        module = importlib.import_module(name)
        monkeypatch.setattr(module, 'CONVERSATION_PATH', tmp_path / 'conversations.jsonl')
        monkeypatch.setattr(module, 'LEGACY_CHAT_PATH', tmp_path / 'legacy-chat.jsonl')
        current = getattr(module.intelligent_answerer, 'memory', None)
        if isinstance(current, module.ConversationMemory):
            # Audio tests assert that tmp_path itself is completely empty.
            runtime_path = tmp_path_factory.mktemp('runtime-memory') / 'conversations.jsonl'
            monkeypatch.setattr(module.intelligent_answerer, 'memory',
                                module.ConversationMemory(context_file=runtime_path))


@pytest.fixture(autouse=True)
def isolated_chat_store(tmp_path_factory, monkeypatch):
    from chat_store import ChatStore
    directory = tmp_path_factory.mktemp('runtime-chats')

    @lru_cache(maxsize=1)
    def test_store():
        return ChatStore(directory)

    for name in ('chat_endpoints', 'backend.chat_endpoints'):
        monkeypatch.setattr(importlib.import_module(name), 'store', test_store)


@pytest.fixture(autouse=True)
def isolated_fact_store(tmp_path, monkeypatch):
    import memories
    monkeypatch.setattr(memories, 'STORE_PATH', tmp_path / 'memories.json')


@pytest.fixture(autouse=True)
def isolated_voice_file(tmp_path, monkeypatch):
    import voice_config
    monkeypatch.setattr(voice_config, "CONFIG_PATH", tmp_path / "voice.json")


@pytest.fixture(scope="session")
def main_module():
    """
    Импортированный main.py.

    Импорт стоит около трёх секунд (поднимаются профиль, база знаний, голос),
    поэтому делается один раз на весь прогон. Сам факт успешного импорта уже
    показателен: именно здесь ловятся обрывы файла и потерянные блоки.
    """
    import main

    # Unit tests must not contact the user's real configured model. Tests of
    # providers and payloads install their own clients explicitly.
    if main.intelligent_answerer:
        main.intelligent_answerer.enabled = False
        main.intelligent_answerer.retry_pending_connection = lambda: False

    return main


@pytest.fixture(scope="session")
def app(main_module):
    return main_module.app


@pytest.fixture(scope="session")
def main_source():
    """Исходный текст main.py — для проверок, которым хватает разбора кода."""
    return (BACKEND_DIR / "main.py").read_text(encoding="utf-8")
