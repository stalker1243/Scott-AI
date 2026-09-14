"""
Что Scott помнит о своём человеке.

Это не та память, что лежит в knowledge_base: там кэш ответов — «на эту фразу
уже отвечали, вот ответ». Здесь другое: сведения о человеке, которые он сам
велел запомнить, и которые Scott учитывает в каждом разговоре.

ЗАЧЕМ ОТДЕЛЬНО. Помощник, которому каждый раз рассказывают одно и то же,
помощником не становится. «Я работаю в вечернюю смену», «мой проект на C#»,
«не люблю длинные ответы» — сказанное однажды должно действовать дальше.

ЧТО ЗДЕСЬ ВАЖНО ПРИ ПРАВКАХ

Записи уходят в КАЖДЫЙ запрос к модели. Поэтому их число и общая длина
ограничены: память, растущая без предела, однажды займёт собой весь запрос и
вытеснит сам вопрос. При переполнении вытесняются самые старые — не самые
редкие: редко нужное всё равно может оказаться важным, а вот забытое полгода
назад обычно устарело.

Удаление — окончательное и без корзины. Человек стирает то, что Scott о нём
знает; предлагать «восстановить» здесь неуместно.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

STORE_PATH = Path(__file__).resolve().parent / "data" / "memories.json"

# Сколько записей уходит в разговор.
#
# Тридцать — это уже длинный список о человеке, и дальше растёт не польза, а
# длина каждого запроса.
MAX_IN_PROMPT = 30

# И сколько знаков они занимают все вместе.
MAX_PROMPT_CHARS = 1500

# Предел на одну запись: память — это короткие сведения, а не дневник.
MAX_TEXT = 200

# Всего записей. Выше этого самые старые вытесняются.
MAX_TOTAL = 200

KINDS = {
    "fact": "Факты",
    "preference": "Предпочтения",
    "task": "Задачи",
    "note": "Заметки",
}

DEFAULT_KIND = "fact"


def _load() -> List[Dict]:
    try:
        if STORE_PATH.exists():
            данные = json.loads(STORE_PATH.read_text(encoding="utf-8"))
            if isinstance(данные, list):
                return [з for з in данные if isinstance(з, dict) and з.get("text")]
    except Exception:
        # Испорченный файл не повод падать при старте: Scott просто ничего не
        # помнит, и это лучше, чем не отвечать вовсе.
        pass
    return []


def _save(записи: List[Dict]) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(записи, ensure_ascii=False, indent=2), encoding="utf-8")


def all_memories() -> List[Dict]:
    """Всё, что Scott помнит, — новое сверху."""
    return sorted(_load(), key=lambda з: з.get("created", 0), reverse=True)


def add(text: str, kind: str = DEFAULT_KIND) -> Dict:
    """
    Запомнить.

    Повторы отбрасываются: человек может сказать «запомни, что я пишу на C#»
    дважды, и два одинаковых пункта в списке выглядят как ошибка программы.
    """
    текст = (text or "").strip()[:MAX_TEXT]
    if not текст:
        return {"success": False, "error": "Нечего запоминать"}

    вид = kind if kind in KINDS else DEFAULT_KIND

    записи = _load()

    for запись in записи:
        if запись.get("text", "").strip().lower() == текст.lower():
            return {"success": True, "memory": запись, "note": "Это Scott уже помнит"}

    запись = {
        "id": uuid.uuid4().hex[:12],
        "text": текст,
        "kind": вид,
        "created": time.time(),
    }

    записи.append(запись)

    # Вытесняем самые старые: забытое полгода назад обычно устарело, а редко
    # нужное всё равно может понадобиться.
    if len(записи) > MAX_TOTAL:
        записи = sorted(записи, key=lambda з: з.get("created", 0))[-MAX_TOTAL:]

    _save(записи)
    return {"success": True, "memory": запись}


def remove(memory_id: str) -> Dict:
    """Забыть одну запись. Окончательно."""
    записи = _load()
    осталось = [з for з in записи if з.get("id") != memory_id]

    if len(осталось) == len(записи):
        return {"success": False, "error": "Такой записи нет"}

    _save(осталось)
    return {"success": True}


def clear(kind: Optional[str] = None) -> Dict:
    """Забыть всё или всё в одной категории."""
    записи = _load()

    if kind is None:
        _save([])
        return {"success": True, "removed": len(записи)}

    осталось = [з for з in записи if з.get("kind") != kind]
    _save(осталось)
    return {"success": True, "removed": len(записи) - len(осталось)}


def describe() -> Dict:
    """Записи вместе с названиями категорий — для интерфейса."""
    записи = all_memories()

    return {
        "memories": записи,
        "kinds": [{"id": ключ, "title": имя} for ключ, имя in KINDS.items()],
        "counts": {ключ: sum(1 for з in записи if з.get("kind") == ключ) for ключ in KINDS},
    }


def prompt_addition() -> str:
    """
    То, что Scott помнит, — словами для модели.

    Пустая строка означает «ничего не менять»: человек, ничего не просивший
    запомнить, должен получать ровно прежнее поведение.

    Записи идут от новых к старым и обрываются по длине: память, растущая без
    предела, однажды вытеснила бы из запроса сам вопрос.
    """
    записи = all_memories()[:MAX_IN_PROMPT]
    if not записи:
        return ""

    строки: List[str] = []
    длина = 0

    for запись in записи:
        строка = f"- {запись['text']}"
        if длина + len(строка) > MAX_PROMPT_CHARS:
            break

        строки.append(строка)
        длина += len(строка)

    if not строки:
        return ""

    return "Вот что человек просил тебя запомнить:\n" + "\n".join(строки)
