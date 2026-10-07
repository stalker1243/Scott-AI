"""Durable complete turns, independent of the model's small context window."""
import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

try:
    from .memory_retrieval import terms, excerpt
except ImportError:
    from memory_retrieval import terms, excerpt

FOLLOWUP = re.compile(r'продолж|обсуждал|говорили|остановились|решили|раньше|прошл', re.I)
FOLLOWUP_TERMS = terms('продолжим продолжить продолжай продолжать продолжение '
                       'обсуждали обсуждал говорили остановились остановился '
                       'решили раньше ранее прошлый прошлое прежде следующий шаг чём чем')


class ConversationArchive:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=3)
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('CREATE TABLE IF NOT EXISTS turns (id INTEGER PRIMARY KEY, fingerprint TEXT UNIQUE, user TEXT NOT NULL, assistant TEXT NOT NULL, timestamp TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS terms (term TEXT NOT NULL, turn_id INTEGER NOT NULL, PRIMARY KEY(term, turn_id))')
            db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS semantic_turns (turn_id INTEGER NOT NULL REFERENCES turns(id) ON DELETE CASCADE, model TEXT NOT NULL, PRIMARY KEY(turn_id,model))')
            db.execute('CREATE TABLE IF NOT EXISTS semantic_chunks (turn_id INTEGER NOT NULL REFERENCES turns(id) ON DELETE CASCADE, ordinal INTEGER NOT NULL, model TEXT NOT NULL, role INTEGER NOT NULL, vector BLOB NOT NULL, PRIMARY KEY(turn_id,ordinal,model))')
            db.execute('CREATE TABLE IF NOT EXISTS chat_sources (fingerprint TEXT PRIMARY KEY REFERENCES turns(fingerprint) ON DELETE CASCADE, chat_id TEXT NOT NULL)')
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _insert(db, user, assistant, timestamp):
        fingerprint = hashlib.sha256(json.dumps([user, assistant, timestamp], ensure_ascii=False).encode('utf-8')).hexdigest()
        cursor = db.execute('INSERT OR IGNORE INTO turns(fingerprint,user,assistant,timestamp) VALUES(?,?,?,?)',
                            (fingerprint, user, assistant, timestamp))
        if cursor.rowcount:
            indexed = terms(user[:20000] + ' ' + assistant[:12000])
            db.executemany('INSERT OR IGNORE INTO terms(term,turn_id) VALUES(?,?)',
                           ((term, cursor.lastrowid) for term in indexed))

    def add(self, user, assistant, timestamp):
        if not user.strip() or not assistant.strip():
            return
        with self.connection() as db:
            self._insert(db, user, assistant, timestamp)
        self.start_semantic_index()

    def remember_chat(self, user, assistant, timestamp, chat_id, existing=False):
        with self.connection() as db:
            row = db.execute('SELECT fingerprint FROM turns WHERE user=? AND assistant=? ORDER BY id DESC LIMIT 1', (user, assistant)).fetchone() if existing else None
            if row:
                fingerprint = row[0]
            else:
                self._insert(db, user, assistant, timestamp)
                fingerprint = hashlib.sha256(json.dumps([user, assistant, timestamp], ensure_ascii=False).encode('utf-8')).hexdigest()
            db.execute('INSERT OR REPLACE INTO chat_sources VALUES(?,?)', (fingerprint, chat_id))
        self.start_semantic_index()

    def bind_chat(self, chat_id, fingerprints):
        with self.connection() as db:
            db.executemany('INSERT OR IGNORE INTO chat_sources VALUES(?,?)', ((fingerprint, chat_id) for fingerprint in fingerprints))

    def delete_chats(self, chat_ids, clear_recent):
        with self.connection() as db:
            if chat_ids is None:
                rows = db.execute('SELECT id,user,assistant FROM turns').fetchall()
            else:
                placeholders = ','.join('?' for _ in chat_ids)
                rows = db.execute(f'SELECT t.id,t.user,t.assistant FROM turns t JOIN chat_sources s ON t.fingerprint=s.fingerprint WHERE s.chat_id IN ({placeholders})', tuple(chat_ids)).fetchall() if chat_ids else []
            db.executemany('DELETE FROM terms WHERE turn_id=?', ((row[0],) for row in rows))
            db.executemany('DELETE FROM turns WHERE id=?', ((row[0],) for row in rows))
            clear_recent({(row[1], row[2]) for row in rows})

    def start_semantic_index(self):
        try:
            from . import semantic_memory
        except ImportError:
            import semantic_memory
        semantic_memory.schedule(self)

    def semantic_status(self):
        try:
            from . import semantic_memory
        except ImportError:
            import semantic_memory
        return semantic_memory.index_status(self)

    def migrate(self, paths, refresh=()):
        """Import both legacy JSONL formats once; leave their files intact."""
        with self.connection() as db:
            for path in map(Path, paths):
                key = 'import:' + str(path.resolve())
                if path not in refresh and db.execute('SELECT 1 FROM metadata WHERE key=?', (key,)).fetchone():
                    continue
                pending = None
                if path.exists():
                    with path.open(encoding='utf-8') as stream:
                        for line in stream:
                            try:
                                row = json.loads(line)
                            except ValueError:
                                continue
                            if not isinstance(row, dict):
                                continue
                            if isinstance(row.get('question'), str) and isinstance(row.get('answer'), str):
                                if row['question'].strip() and row['answer'].strip():
                                    self._insert(db, row['question'], row['answer'], str(row.get('timestamp', '')))
                            elif isinstance(row.get('content'), str) and row['content'].strip():
                                if row.get('role') == 'user':
                                    pending = row
                                elif row.get('role') == 'assistant' and pending:
                                    self._insert(db, pending['content'], row['content'], str(pending.get('timestamp', '')))
                                    pending = None
                db.execute('INSERT OR REPLACE INTO metadata(key,value) VALUES(?,?)', (key, 'done'))

    def recent(self, limit=10):
        with self.connection() as db:
            return list(reversed(db.execute('SELECT user,assistant,timestamp FROM turns ORDER BY id DESC LIMIT ?', (limit,)).fetchall()))

    def count(self):
        with self.connection() as db:
            return db.execute('SELECT COUNT(*) FROM turns').fetchone()[0]

    def recall(self, query, excluded=(), max_chars=2000):
        followup = bool(FOLLOWUP.search(query))
        keywords = terms(query)
        if followup:
            keywords -= FOLLOWUP_TERMS
        wanted = sorted(keywords)[:20]
        try:
            from . import semantic_memory
        except ImportError:
            import semantic_memory
        self.start_semantic_index()
        similarities = semantic_memory.candidates(self, query)
        with self.connection() as db:
            rows = []
            if wanted:
                placeholders = ','.join('?' for _ in wanted)
                rows = db.execute(f'SELECT t.id,t.user,t.assistant,t.timestamp FROM turns t JOIN terms s ON s.turn_id=t.id WHERE s.term IN ({placeholders}) GROUP BY t.id ORDER BY COUNT(*) DESC,t.id DESC LIMIT 40', wanted).fetchall()
            if followup:
                # A named topic may be much older than the last forty turns.
                # Keep a recent fallback for "continue", but rank topic matches
                # ahead of unrelated conversations when the query names one.
                recent = db.execute('SELECT id,user,assistant,timestamp FROM turns ORDER BY id DESC LIMIT 40').fetchall()
                rows = list({row[0]: row for row in [*rows, *recent]}.values())
            if similarities:
                placeholders = ','.join('?' for _ in similarities)
                semantic_rows = db.execute(f'SELECT id,user,assistant,timestamp FROM turns WHERE id IN ({placeholders})', list(similarities)).fetchall()
                rows = list({row[0]: row for row in [*rows, *semantic_rows]}.values())
            if not rows:
                return []
        wanted_set = set(wanted)
        rows.sort(key=lambda row: (len(terms(row[1]) & wanted_set) * 3 + len(terms(row[2]) & wanted_set)
                                  + similarities.get(row[0], 0) * 12, row[0]), reverse=True)
        excluded = set(excluded)
        try:
            from .memories import history_allowed
        except ImportError:
            from memories import history_allowed
        selected, size = [], 0
        for ident, user, assistant, timestamp in rows:
            pair = (user, assistant)
            if pair in excluded or not history_allowed(user, assistant):
                continue
            excluded.add(pair)
            question = excerpt(user, query, 450)
            answer = excerpt(assistant, query, 650)
            user_content = f'[Ранний разговор {timestamp[:10]}]\n{question}'
            cost = len(user_content) + len(answer)
            if size + cost > max_chars:
                continue
            selected.append((ident, {'role': 'user', 'content': user_content}, {'role': 'assistant', 'content': answer}))
            size += cost
            if len(selected) == 4:
                break
        return [message for _, user, assistant in sorted(selected) for message in (user, assistant)]

    def clear(self, clear_recent):
        # If the recent-file write fails, SQLite rolls back too.
        with self.connection() as db:
            db.execute('DELETE FROM terms')
            db.execute('DELETE FROM turns')
            clear_recent()
