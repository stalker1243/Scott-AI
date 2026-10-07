"""
Что Scott помнит о своём человеке.

Здесь хранятся сведения, добавленные вручную или явно сказанные человеком
в диалоге. Старые факты выбираются по теме вопроса, а не только по дате.
Полная история завершённых разговоров хранится отдельно в SQLite.

ЗАЧЕМ ОТДЕЛЬНО. Помощник, которому каждый раз рассказывают одно и то же,
помощником не становится. «Я работаю в вечернюю смену», «мой проект на C#»,
«не люблю длинные ответы» — сказанное однажды должно действовать дальше.

ЧТО ЗДЕСЬ ВАЖНО ПРИ ПРАВКАХ

Размер добавки к запросу ограничен. При заполнении списка сначала вытесняются
автоматические факты; явно сохранённые человеком записи имеют приоритет.

Удаление — окончательное и без корзины. Человек стирает то, что Scott о нём
знает; предлагать «восстановить» здесь неуместно.
"""

from __future__ import annotations

import json
import time
import uuid
import threading
import hashlib
import re
from functools import wraps
from pathlib import Path
from typing import Dict, List, Optional
try:
    from .storage import atomic_write_text
except ImportError:
    from storage import atomic_write_text

_store_lock = threading.RLock()


def _mutate(operation):
    @wraps(operation)
    def run(*args, **kwargs):
        with _store_lock:
            try:
                return operation(*args, **kwargs)
            except (OSError, ValueError):
                return {"success": False, "error": "Не удалось сохранить память. Проверьте файл памяти и доступ к папке данных"}
    return run

STORE_PATH = Path(__file__).resolve().parent / "data" / "memories.json"

# Сколько записей уходит в разговор.
#
# Тридцать — это уже длинный список о человеке, и дальше растёт не польза, а
# длина каждого запроса.
MAX_IN_PROMPT = 30

# И сколько знаков они занимают все вместе.
MAX_PROMPT_CHARS = 2500

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


def _load(strict: bool = False) -> List[Dict]:
    try:
        if STORE_PATH.exists():
            данные = json.loads(STORE_PATH.read_text(encoding="utf-8"))
            if isinstance(данные, list):
                return [з for з in данные if isinstance(з, dict) and isinstance(з.get("text"), str) and з["text"].strip()]
            if strict:
                raise ValueError("Invalid memory store")
    except (OSError, ValueError):
        # Испорченный файл не повод падать при старте: Scott просто ничего не
        # помнит, и это лучше, чем не отвечать вовсе.
        if strict:
            raise
    return []


def _save(записи: List[Dict]) -> None:
    atomic_write_text(STORE_PATH, json.dumps(записи, ensure_ascii=False, indent=2))
    try:
        from . import semantic_memory
    except ImportError:
        import semantic_memory
    semantic_memory.clear_fact_cache()


def all_memories() -> List[Dict]:
    """Всё, что Scott помнит, — новое сверху."""
    with _store_lock:
        return sorted(_load(), key=lambda з: з.get('updated', з.get("created", 0)), reverse=True)


@_mutate
def add(text: str, kind: str = DEFAULT_KIND, *, source='manual', key='') -> Dict:
    """
    Запомнить.

    Повторы отбрасываются: человек может сказать «запомни, что я пишу на C#»
    дважды, и два одинаковых пункта в списке выглядят как ошибка программы.
    """
    текст = (text or "").strip()[:MAX_TEXT]
    if not текст:
        return {"success": False, "error": "Нечего запоминать"}

    вид = kind if kind in KINDS else DEFAULT_KIND
    try:
        from .memory_facts import extract
    except ImportError:
        from memory_facts import extract
    inferred = extract(текст)
    key = key or (inferred[0]['key'] if len(inferred) == 1 else '')

    записи = _load(strict=True)

    for запись in записи:
        if запись.get("text", "").strip().lower() == текст.lower():
            return {"success": True, "memory": запись, "note": "Это Scott уже помнит"}
        old_keys = [fact['key'] for fact in extract(запись.get('text', ''))]
        if key and (запись.get('key') == key or key in old_keys):
            origin = 'manual' if запись.get('source', 'manual') == 'manual' else source
            запись.update(text=текст, kind=вид, key=key, source=origin, updated=time.time())
            _save(записи)
            return {'success': True, 'memory': запись, 'note': 'Сведения обновлены'}

    if source == 'conversation' and len(записи) >= MAX_TOTAL and not any(row.get('source') == 'conversation' for row in записи):
        return {'success': False, 'error': 'Память заполнена сохранёнными вручную фактами'}

    запись = {
        "id": uuid.uuid4().hex[:12],
        "text": текст,
        "kind": вид,
        "created": time.time(),
        'source': source,
        'key': key,
    }

    записи.append(запись)

    # Вытесняем самые старые: забытое полгода назад обычно устарело, а редко
    # нужное всё равно может понадобиться.
    if len(записи) > MAX_TOTAL:
        записи = sorted(записи, key=lambda з: (
            2 if з.get('source') != 'conversation' else
            1 if з.get('key', '').startswith('profile:') or з.get('key') == 'preference:response_style' else 0,
            з.get('updated', з.get("created", 0))))[-MAX_TOTAL:]

    _save(записи)
    return {"success": True, "memory": запись}


@_mutate
def remove(memory_id: str) -> Dict:
    """Забыть одну запись. Окончательно."""
    записи = _load(strict=True)
    осталось = [з for з in записи if з.get("id") != memory_id]

    if len(осталось) == len(записи):
        return {"success": False, "error": "Такой записи нет"}

    _suppress_history([row for row in записи if row.get('id') == memory_id])
    _save(осталось)
    return {"success": True}


@_mutate
def clear(kind: Optional[str] = None) -> Dict:
    """Забыть всё или всё в одной категории."""
    записи = _load(strict=kind is not None)

    if kind is None:
        _suppress_history(записи)
        _save([])
        return {"success": True, "removed": len(записи)}

    осталось = [з for з in записи if з.get("kind") != kind]
    _suppress_history([row for row in записи if row.get('kind') == kind])
    _save(осталось)
    return {"success": True, "removed": len(записи) - len(осталось)}


def describe() -> Dict:
    """Записи вместе с названиями категорий — для интерфейса."""
    записи = all_memories()

    warning = ''
    try:
        with _store_lock:
            _load(strict=True)
    except (OSError, ValueError):
        warning = 'Файл фактов недоступен или повреждён. Новые сведения не будут сохранены.'
    if settings().get('unavailable'):
        warning = 'Настройки памяти недоступны или повреждены.'
    return {
        "memories": записи,
        "kinds": [{"id": ключ, "title": имя} for ключ, имя in KINDS.items()],
        "counts": {ключ: sum(1 for з in записи if з.get("kind") == ключ) for ключ in KINDS},
        'auto_capture': settings()['auto_capture'],
        'warning': warning,
    }


def prompt_addition(query: str = '') -> str:
    """
    То, что Scott помнит, — словами для модели.

    Пустая строка означает «ничего не менять»: человек, ничего не просивший
    запомнить, должен получать ровно прежнее поведение.

    Записи идут от новых к старым и обрываются по длине: память, растущая без
    предела, однажды вытеснила бы из запроса сам вопрос.
    """
    записи = all_memories()
    if query:
        try:
            from .memory_retrieval import terms
        except ImportError:
            from memory_retrieval import terms
        wanted = terms(query)
        try:
            from . import semantic_memory
        except ImportError:
            import semantic_memory
        similarities = semantic_memory.fact_scores(query, записи)
        try:
            from .memory_facts import extract
        except ImportError:
            from memory_facts import extract
        def fact_key(row):
            if row.get('key'):
                return row['key']
            inferred = extract(row['text'])
            return inferred[0]['key'] if len(inferred) == 1 else ''
        # Relevance wins over recency. Core profile facts remain available
        # even for follow-up questions without an explicit subject.
        записи.sort(key=lambda row: (
            len(terms(row['text']) & wanted) * 4
            + similarities.get(row.get('id'), 0) * 12
            + (100 if fact_key(row) in ('profile:name', 'preference:response_style') else 0)
            + (2 if fact_key(row).startswith('project:') else 0),
            row.get('updated', row.get('created', 0))), reverse=True)
    записи = записи[:MAX_IN_PROMPT]
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

    return ('Сохранённые сведения из слов пользователя. Учитывай последнее уточнение; '
            'если нужных сведений нет, не выдумывай их:\n' + '\n'.join(строки))


def answer(query):
    """Answer only exact profile questions using saved user declarations."""
    try:
        from .memory_facts import extract
    except ImportError:
        from memory_facts import extract
    query = query.casefold().strip(' .!?')
    query = re.sub(r'^(?:скотт|скот|scott)[,\s]+', '', query)
    rows = all_memories()
    if re.fullmatch(r'(?:скажи,?\s+)?(?:как меня зовут|какое у меня имя|какое мо[её] имя)', query):
        key, prefix = 'profile:name', 'Тебя зовут '
    elif re.fullmatch(r'(?:скажи,?\s+)?(?:где я живу|в каком городе я живу)', query):
        key, prefix = 'profile:location', 'Ты живёшь '
    elif re.fullmatch(r'что ты (?:обо мне помнишь|помнишь обо мне|знаешь обо мне)', query):
        return 'Вот что сохранено в памяти:\n' + '\n'.join('- ' + row['text'] for row in rows[:10]) if rows else None
    else:
        return None
    for row in rows:
        for fact in extract(row['text']):
            if fact['key'] == key:
                return prefix + fact['value'].rstrip('.!?') + '.'
    return None


def _settings_path():
    return STORE_PATH.with_suffix('.settings.json')


def settings(strict=False):
    with _store_lock:
        try:
            data = json.loads(_settings_path().read_text(encoding='utf-8'))
            if not isinstance(data, dict) or not isinstance(data.get('auto_capture', True), bool):
                raise ValueError('Invalid memory settings')
            if any(not isinstance(data.get(field, []), list) or any(not isinstance(value, str) for value in data.get(field, []))
                   for field in ('suppressed_keys', 'suppressed_hashes')):
                raise ValueError('Invalid memory redactions')
            return {'auto_capture': data.get('auto_capture', True),
                    'suppressed_keys': data.get('suppressed_keys', []), 'suppressed_hashes': data.get('suppressed_hashes', [])}
        except FileNotFoundError:
            return {'auto_capture': True, 'suppressed_keys': [], 'suppressed_hashes': []}
        except (OSError, ValueError):
            if strict:
                raise
            return {'auto_capture': False, 'suppressed_keys': [], 'suppressed_hashes': [], 'unavailable': True}


def _save_settings(data):
    atomic_write_text(_settings_path(), json.dumps(data, ensure_ascii=False, indent=2))


@_mutate
def set_auto_capture(enabled):
    if not isinstance(enabled, bool):
        return {'success': False, 'error': 'auto_capture должен быть true или false'}
    data = settings(strict=True)
    data['auto_capture'] = enabled
    _save_settings(data)
    return {'success': True, 'auto_capture': enabled}


def observe(text):
    if not isinstance(text, str) or not settings()['auto_capture']:
        return []
    try:
        from .memory_facts import extract
    except ImportError:
        from memory_facts import extract
    return [add(fact['text'], fact['kind'], source='conversation', key=fact['key']) for fact in extract(text[:20000])]


def _text_hash(text):
    normalized = re.sub(r'\W+', ' ', text.casefold().replace('ё', 'е')).strip()
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def _suppress_history(rows):
    if not rows:
        return
    try:
        from .memory_facts import extract
    except ImportError:
        from memory_facts import extract
    data = settings(strict=True)
    keys = set(data['suppressed_keys'])
    hashes = set(data['suppressed_hashes'])
    for row in rows:
        extracted = extract(row['text'])
        keys.update(fact['key'] for fact in extracted)
        for fact in extracted:
            if fact['key'] == 'profile:name':
                hashes.add(_text_hash(fact['value']))
        if row.get('key'):
            keys.add(row['key'])
        hashes.add(_text_hash(row['text']))
    data.update(suppressed_keys=sorted(keys), suppressed_hashes=sorted(hashes))
    _save_settings(data)


def history_allowed(user, assistant):
    """A deleted fact must not be silently supplied again from an old turn."""
    data = settings()
    if data.get('unavailable'):
        return False
    if not data['suppressed_keys'] and not data['suppressed_hashes']:
        return True
    hashes = set(data['suppressed_hashes'])
    try:
        from .memory_facts import extract
    except ImportError:
        from memory_facts import extract
    if any(fact['key'] in data['suppressed_keys'] for fact in extract(user)):
        return False
    if 'profile:name' in data['suppressed_keys'] and re.search(r'меня зовут|мо[её] имя|мо[её]м имени', user, re.I):
        return False
    candidates = re.split(r'(?<=[.!?])\s+|\n+', user + '\n' + assistant)
    for candidate in candidates:
        candidate = re.sub(r'^\s*(?:запомни|помни|запиши)(?:те)?[,\s]*(?:что\s+)?', '', candidate, flags=re.I)
        if _text_hash(candidate[:MAX_TEXT]) in hashes:
            return False
        words = re.findall(r'\w+', candidate)
        for size in (1, 2, 3):
            if any(_text_hash(' '.join(words[i:i + size])) in hashes for i in range(len(words) - size + 1)):
                return False
    return True
