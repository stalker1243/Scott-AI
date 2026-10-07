"""Persistent named chats, bounded context and locally owned media assets."""
import json
import hashlib
import base64
import sqlite3
import uuid
from contextlib import contextmanager, closing
from pathlib import Path
from datetime import datetime, timezone

DEFAULT_CHAT_DIR = Path(__file__).resolve().parent / 'data' / 'chats'

def now():
    return datetime.now(timezone.utc).isoformat()


class ChatStore:
    def __init__(self, directory=None):
        self.directory = (Path(directory) if directory is not None else DEFAULT_CHAT_DIR).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.assets = self.directory / 'assets'
        self.assets.mkdir(exist_ok=True)
        self.path = self.directory / 'chats.sqlite3'
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS chats(id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    created TEXT NOT NULL, updated TEXT NOT NULL, renamed INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, chat_id TEXT NOT NULL
                    REFERENCES chats(id) ON DELETE CASCADE, role TEXT NOT NULL, text TEXT NOT NULL,
                    content TEXT NOT NULL, attachments TEXT NOT NULL, model TEXT NOT NULL, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY, chat_id TEXT NOT NULL
                    REFERENCES chats(id) ON DELETE CASCADE, mime TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            with db:
                yield db
        finally:
            db.close()

    def list(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('''SELECT c.*, COUNT(m.id) AS count
                FROM chats c LEFT JOIN messages m ON c.id=m.chat_id
                GROUP BY c.id ORDER BY c.updated DESC LIMIT 500''')]

    def import_legacy(self, archive_path):
        """Copy the pre-session transcript once; never touch the original memory."""
        if not archive_path or not Path(archive_path).is_file():
            return
        with self.connect() as db:
            marker = db.execute("SELECT value FROM metadata WHERE key='legacy_import'").fetchone()
            if marker:
                ident = marker['value']
                if db.execute("SELECT 1 FROM metadata WHERE key='legacy_bound'").fetchone() or not db.execute('SELECT 1 FROM chats WHERE id=?', (ident,)).fetchone():
                    return
                messages = list(db.execute('SELECT role,text,created FROM messages WHERE chat_id=? ORDER BY id', (ident,)))
                fingerprints = [hashlib.sha256(json.dumps([u['text'], a['text'], u['created']], ensure_ascii=False).encode('utf-8')).hexdigest() for u, a in zip(messages[::2], messages[1::2])]
                return ident, fingerprints
            with closing(sqlite3.connect('file:' + Path(archive_path).resolve().as_posix() + '?mode=ro', uri=True)) as source:
                rows = list(source.execute('SELECT user, assistant, timestamp, fingerprint FROM turns ORDER BY id'))
            if rows:
                ident, timestamp = uuid.uuid4().hex, now()
                db.execute('INSERT INTO chats VALUES(?,?,?,?,1)', (ident, 'Предыдущая переписка', timestamp, timestamp))
                for user, assistant, created, _ in rows:
                    for role, text in [('user', user), ('assistant', assistant)]:
                        db.execute('INSERT INTO messages(chat_id,role,text,content,attachments,model,created) VALUES(?,?,?,?,?,?,?)',
                                   (ident, role, text, json.dumps(text, ensure_ascii=False), '[]', '', created))
            db.execute("INSERT INTO metadata VALUES('legacy_import',?)", (ident if rows else 'none',))
        return (ident, [row[3] for row in rows]) if rows else None

    def mark_legacy_bound(self):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO metadata VALUES('legacy_bound','1')")

    def create(self):
        ident, timestamp = uuid.uuid4().hex, now()
        with self.connect() as db:
            db.execute('INSERT INTO chats VALUES(?,?,?,?,0)', (ident, 'Новый диалог', timestamp, timestamp))
        return self.get(ident)

    def get(self, ident):
        with self.connect() as db:
            row = db.execute('SELECT * FROM chats WHERE id=?', (ident,)).fetchone()
            if row is None:
                raise KeyError('Диалог не найден')
            chat = dict(row)
            chat['messages'] = []
            for message in db.execute('SELECT * FROM messages WHERE chat_id=? ORDER BY id', (ident,)):
                entry = dict(message)
                entry['attachments'] = json.loads(entry['attachments'])
                entry.pop('content')
                chat['messages'].append(entry)
        return chat

    def context(self, ident, images=False):
        with self.connect() as db:
            rows = list(db.execute('SELECT role, content, attachments FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT 20', (ident,)))
        result, size, images_used = [], 0, False
        # Include the latest image attachment again on follow-up questions, only
        # when the newly selected model supports vision. Videos stay single-turn.
        for user, assistant in zip(rows[1::2], rows[::2]):
            pair = [dict(role=r['role'], content=json.loads(r['content'])) for r in (user, assistant)]
            weight = len(json.dumps(pair, ensure_ascii=False))
            if size + weight > 32000:
                if result:
                    break
                pair[0]['content'] = pair[0]['content'][:24000]
                pair[1]['content'] = pair[1]['content'][:6000]
                weight = len(json.dumps(pair, ensure_ascii=False))
            size += weight
            if images and not images_used:
                parts, byte_count = [], 0
                for asset in json.loads(user['attachments']):
                    if asset['mime'].startswith('image/'):
                        path, mime = self.asset(asset['url'].rsplit('/', 1)[-1])
                        data = path.read_bytes()
                        byte_count += len(data)
                        if byte_count > 20 * 1024 * 1024:
                            break
                        parts.append(dict(type='image_url', image_url=dict(url='data:' + mime + ';base64,' + base64.b64encode(data).decode('ascii'))))
                if parts:
                    pair[0]['content'] = [dict(type='text', text=pair[0]['content'])] + parts
                    images_used = True
            result[0:0] = pair
        return result

    def rename(self, ident, title):
        title = title.strip()
        if not title or len(title) > 100 or any(ord(c) < 32 for c in title):
            raise ValueError('Название: от 1 до 100 символов, одной строкой')
        self.get(ident)
        with self.connect() as db:
            db.execute('UPDATE chats SET title=?, renamed=1 WHERE id=?', (title, ident))
        return self.get(ident)

    def delete(self, ident=None, clear=False):
        with self.connect() as db:
            assets = list(db.execute('SELECT id FROM assets' + (' WHERE chat_id=?' if ident else ''), (ident,) if ident else ()))
            if ident:
                self.get(ident)
            if clear and ident:
                db.execute('DELETE FROM messages WHERE chat_id=?', (ident,))
                db.execute('DELETE FROM assets WHERE chat_id=?', (ident,))
                db.execute('UPDATE chats SET updated=? WHERE id=?', (now(), ident))
            else:
                db.execute('DELETE FROM chats' + (' WHERE id=?' if ident else ''), (ident,) if ident else ())
        for row in assets:
            (self.assets / row['id']).unlink(missing_ok=True)

    def asset(self, ident):
        with self.connect() as db:
            row = db.execute('SELECT mime FROM assets WHERE id=?', (ident,)).fetchone()
        if row is None or not (self.assets / ident).is_file():
            raise KeyError('Изображение не найдено')
        return self.assets / ident, row['mime']

    def commit_turn(self, ident, question, context, answer, model, media):
        timestamp, written, attachment_rows = now(), [], []
        try:
            with self.connect() as db:
                chat = db.execute('SELECT * FROM chats WHERE id=?', (ident,)).fetchone()
                if not chat:
                    raise KeyError('Диалог не найден')
                for role, name, mime, data in media:
                    asset_id = uuid.uuid4().hex
                    (self.assets / asset_id).write_bytes(data)
                    written.append(self.assets / asset_id)
                    db.execute('INSERT INTO assets VALUES(?,?,?)', (asset_id, ident, mime))
                    attachment_rows.append(dict(role=role, name=name, mime=mime, url='/chats/assets/' + asset_id))
                for role, text, content in [('user', question, context), ('assistant', answer, answer)]:
                    db.execute('INSERT INTO messages(chat_id,role,text,content,attachments,model,created) VALUES(?,?,?,?,?,?,?)',
                               (ident, role, text, json.dumps(content, ensure_ascii=False),
                                json.dumps([a for a in attachment_rows if a['role'] == role], ensure_ascii=False), model, timestamp))
                title = chat['title']
                if not chat['renamed'] and not db.execute('SELECT 1 FROM messages WHERE chat_id=? LIMIT 1 OFFSET 2', (ident,)).fetchone():
                    title = ' '.join(question.split())[:60] or 'Диалог с вложениями'
                db.execute('UPDATE chats SET title=?, updated=? WHERE id=?', (title, timestamp, ident))
            return self.get(ident)
        except Exception:
            for path in written:
                path.unlink(missing_ok=True)
            raise
