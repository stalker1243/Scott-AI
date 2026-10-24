"""Durable at-most-once chat requests; an unknown outcome is never replayed."""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
import re
import uuid

OWNER = uuid.uuid4().hex  # A new backend process cannot inherit a live request.
_active = ContextVar('chat_receipt', default=None)


class ReceiptConflict(ValueError):
    pass


def valid_id(value):
    return isinstance(value, str) and re.fullmatch(r'[a-f0-9]{32}', value) is not None


def fingerprint(question, mode, payload):
    fields = [question.strip(), mode, [(name, hashlib.sha256(data).hexdigest()) for name, data in payload]]
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def claim(store, chat_id, ident, digest, question):
    if not valid_id(ident):
        raise ValueError('Некорректный идентификатор сообщения')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM chats WHERE id=?', (chat_id,)).fetchone():
            raise KeyError('Диалог не найден')
        row = db.execute('SELECT * FROM requests WHERE id=?', (ident,)).fetchone()
        if row:
            if row['chat_id'] == chat_id and row['state'] == 'cleared':
                raise ReceiptConflict(message('cleared'))
            if row['chat_id'] != chat_id or row['fingerprint'] != digest:
                raise ReceiptConflict('Идентификатор уже относится к другому сообщению. Создайте новый запрос.')
            state = public_state(row)
            if state == 'failed':
                db.execute("UPDATE requests SET state='pending',owner=?,phase='pending' WHERE id=?", (OWNER, ident))
                return True
            if state != 'completed':
                raise ReceiptConflict(message(state))
            return False
        db.execute('INSERT INTO requests(id,chat_id,fingerprint,question,state,owner) VALUES(?,?,?,?,?,?)',
                   (ident, chat_id, digest, question.strip(), 'pending', OWNER))
    return True


def public_state(row):
    if row['state'] == 'pending':
        return 'running' if row['owner'] == OWNER else 'uncertain'
    return row['state']


def message(state):
    if state == 'running':
        return 'Запрос ещё выполняется. Повторно отправлять его не нужно.'
    if state == 'cleared':
        return 'История этого запроса очищена. Он не будет выполнен повторно.'
    if state == 'failed':
        return 'Запрос не завершён. Сообщение сохранено, можно повторить отправку.'
    return 'Связь прервалась, результат запроса неизвестен. Проверьте действие и историю перед новым запросом. Автоматического повтора нет.'


def status(store, chat_id, ident):
    if not valid_id(ident):
        raise KeyError('Запрос не найден')
    with store.connect() as db:
        row = db.execute('SELECT * FROM requests WHERE id=? AND chat_id=?', (ident, chat_id)).fetchone()
    if not row:
        raise KeyError('Запрос не найден')
    state = public_state(row)
    return dict(id=ident, state=state, question=row['question'], message='' if state == 'completed' else message(state))


@contextmanager
def scope(store, ident):
    token = _active.set((str(store.path), ident))
    try:
        yield
    finally:
        _active.reset(token)


def interrupted(store, ident):
    # A worker may still be finishing after cancellation. It can commit its
    # result, but a new HTTP request cannot execute this ID again.
    with store.connect() as db:
        db.execute("UPDATE requests SET state=CASE WHEN phase='effect' THEN 'uncertain' ELSE 'failed' END WHERE id=? AND state='pending' AND owner=?", (ident, OWNER))


def phase(store, value):
    active = _active.get()
    if active and active[0] == str(store.path):
        with store.connect() as db:
            db.execute('UPDATE requests SET phase=? WHERE id=? AND owner=?', (value, active[1], OWNER))


def commit(db, store, chat_id):
    active = _active.get()
    if not active or active[0] != str(store.path):
        return
    ident = active[1]
    row = db.execute('SELECT state,owner,chat_id FROM requests WHERE id=?', (ident,)).fetchone()
    if not row or row['owner'] != OWNER or row['chat_id'] != chat_id or row['state'] not in ('pending', 'uncertain'):
        raise ReceiptConflict('Запрос уже завершён или больше не актуален.')
    db.execute("UPDATE requests SET state='completed',question='' WHERE id=?", (ident,))
