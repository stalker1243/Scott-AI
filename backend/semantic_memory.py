"""Local multilingual embeddings and background indexing; no chat API calls."""
from collections import OrderedDict
import os
from pathlib import Path
import threading
import time

MODEL_ID = 'intfloat/multilingual-e5-small'
REVISION = '614241f622f53c4eeff9890bdc4f31cfecc418b3'
MODEL_FILE = 'onnx/model_qint8_avx512_vnni.onnx'
MODEL_KEY = f'{MODEL_ID}@{REVISION}:qint8:mean128:query-passage:v1'
MODEL_DIR = Path(__file__).resolve().parent / 'data' / 'semantic-model' / REVISION
DIMENSIONS = 384
MIN_SIMILARITY = 0.80
_lock = threading.RLock()
_load_lock = threading.Lock()
_encoder = None
_state = 'not_loaded'
_retry_after = 0
_jobs = {}
_index_errors = {}
_fact_cache = OrderedDict()
_fact_epoch = 0


def enabled():
    return os.getenv('SCOTT_SEMANTIC_MEMORY', '1').strip().lower() not in ('0', 'false', 'off')


class Encoder:
    def __init__(self, download=True):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        if download:
            from huggingface_hub import hf_hub_download
            for filename in ('tokenizer.json', MODEL_FILE):
                if not (MODEL_DIR / filename).is_file():
                    hf_hub_download(MODEL_ID, filename, revision=REVISION,
                                    local_dir=str(MODEL_DIR), token=False, etag_timeout=10)
        self.tokenizer = Tokenizer.from_file(str(MODEL_DIR / 'tokenizer.json'))
        self.tokenizer.enable_truncation(max_length=128)
        pad_token = '<pad>' if self.tokenizer.token_to_id('<pad>') is not None else '[PAD]'
        self.tokenizer.enable_padding(pad_id=self.tokenizer.token_to_id(pad_token), pad_token=pad_token)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(MODEL_DIR / MODEL_FILE), options,
                                           providers=['CPUExecutionProvider'])
        self.inputs = {item.name for item in self.session.get_inputs()}
        self.lock = threading.Lock()

    def encode(self, texts, query=False):
        import numpy as np
        batches = []
        for start in range(0, len(texts), 8):
            # Hold the shared tokenizer only for one small batch, so queries
            # can run between background indexing batches.
            with self.lock:
                prefix = 'query: ' if query else 'passage: '
                tokens = self.tokenizer.encode_batch([prefix + text for text in texts[start:start + 8]])
                feed = {'input_ids': np.array([item.ids for item in tokens], dtype=np.int64),
                        'attention_mask': np.array([item.attention_mask for item in tokens], dtype=np.int64),
                        'token_type_ids': np.array([item.type_ids for item in tokens], dtype=np.int64)}
                mask = feed['attention_mask'][..., None].astype(np.float32)
                output = self.session.run(None, {key: value for key, value in feed.items() if key in self.inputs})[0]
                pooled = (output * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1)
                vectors = pooled / np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-9)
                if vectors.shape[1] != DIMENSIONS or not np.isfinite(vectors).all():
                    raise ValueError('Invalid semantic vectors')
                batches.append(vectors.astype('<f4'))
        return np.concatenate(batches) if batches else np.empty((0, DIMENSIONS), dtype='<f4')


def load(download=True):
    global _encoder, _state, _retry_after
    if not enabled():
        return None
    with _load_lock:
        with _lock:
            if _encoder is not None:
                return _encoder
            if time.monotonic() < _retry_after:
                return None
            _state = 'loading'
        try:
            candidate = Encoder(download=download)
        except Exception:
            with _lock:
                _state = 'unavailable'
                _retry_after = time.monotonic() + 300
            return None
        with _lock:
            _encoder, _state = candidate, 'ready'
            return _encoder


def get_encoder():
    with _lock:
        return _encoder if enabled() else None


def status():
    with _lock:
        return {'state': _state if enabled() else 'disabled', 'model': MODEL_ID,
                'device': 'cpu', 'revision': REVISION}


def chunks(text):
    # Keep distant details in separate passages, instead of silently encoding
    # only the beginning of a long conversation.
    text = text[:6000]
    return [text[start:start + 420] for start in range(0, len(text), 360) if text[start:start + 420].strip()]


def schedule(archive):
    if not enabled():
        return
    path = str(archive.path.resolve())
    with _lock:
        job = _jobs.get(path)
        if job is not None:
            job['dirty'] = True
            return
        if time.monotonic() < _retry_after:
            return
        if time.monotonic() - _index_errors.get(path, -1000) < 60:
            return
        job = {'dirty': True}
        _jobs[path] = job
    threading.Thread(target=_index, args=(archive, path, job), daemon=True,
                     name='semantic-memory-index').start()


def _index(archive, path, job):
    try:
        encoder = load()
        if encoder is None:
            return
        while enabled():
            with _lock:
                job['dirty'] = False
            while enabled():
                with archive.connection() as db:
                    rows = db.execute('SELECT t.id,t.fingerprint,t.user,t.assistant FROM turns t '
                                      'WHERE NOT EXISTS (SELECT 1 FROM semantic_turns s '
                                      'WHERE s.turn_id=t.id AND s.model=?) ORDER BY t.id LIMIT 8',
                                      (MODEL_KEY,)).fetchall()
                if not rows:
                    break
                for ident, fingerprint, user, assistant in rows:
                    passages = [(0, text) for text in chunks(user)] + [(1, text) for text in chunks(assistant)]
                    vectors = encoder.encode([text for _, text in passages])
                    if len(vectors) != len(passages):
                        raise ValueError('Incomplete semantic vectors')
                    with archive.connection() as db:
                        # Clear/history replacement may happen while encoding.
                        # Check identity inside the write transaction, including
                        # when SQLite reuses an ID after clearing all turns.
                        db.execute('BEGIN IMMEDIATE')
                        current = db.execute('SELECT fingerprint FROM turns WHERE id=?', (ident,)).fetchone()
                        if current != (fingerprint,):
                            continue
                        db.executemany('INSERT OR REPLACE INTO semantic_chunks(turn_id,ordinal,model,role,vector) VALUES(?,?,?,?,?)',
                                       ((ident, ordinal, MODEL_KEY, role, vector.tobytes())
                                        for ordinal, ((role, _), vector) in enumerate(zip(passages, vectors))))
                        db.execute('INSERT OR REPLACE INTO semantic_turns(turn_id,model) VALUES(?,?)', (ident, MODEL_KEY))
            with _lock:
                if not job['dirty']:
                    # Remove under the same lock as schedule(), so a completed
                    # job cannot lose a just-added turn.
                    _index_errors.pop(path, None)
                    if _jobs.get(path) is job:
                        del _jobs[path]
                    return
    except Exception:
        # The keyword index and original conversations remain usable.
        with _lock:
            _index_errors[path] = time.monotonic()
    finally:
        with _lock:
            if _jobs.get(path) is job:
                _jobs.pop(path, None)


def index_status(archive):
    result = status()
    path = str(archive.path.resolve())
    with _lock:
        if enabled() and result['state'] == 'ready':
            if path in _jobs:
                result['state'] = 'indexing'
            elif path in _index_errors:
                result['state'] = 'unavailable'
    try:
        with archive.connection() as db:
            result['indexed_turns'] = db.execute('SELECT COUNT(*) FROM semantic_turns WHERE model=?', (MODEL_KEY,)).fetchone()[0]
            result['total_turns'] = db.execute('SELECT COUNT(*) FROM turns').fetchone()[0]
    except Exception:
        result.update(state='unavailable', indexed_turns=0, total_turns=0)
    return result


def candidates(archive, query, limit=40):
    encoder = get_encoder()
    if encoder is None or not query.strip():
        return {}
    try:
        import numpy as np
        vector = encoder.encode([query], query=True)[0]
        scores = {}
        with archive.connection() as db:
            cursor = db.execute('SELECT turn_id,role,vector FROM semantic_chunks WHERE model=?', (MODEL_KEY,))
            while rows := cursor.fetchmany(256):
                valid = [(ident, role, np.frombuffer(blob, dtype='<f4')) for ident, role, blob in rows
                         if len(blob) == DIMENSIONS * 4]
                if not valid:
                    continue
                matrix = np.stack([row[2] for row in valid])
                similarities = matrix @ vector
                for (ident, role, _), similarity in zip(valid, similarities):
                    value = float(similarity)
                    if np.isfinite(value) and value >= MIN_SIMILARITY:
                        scores[ident] = max(scores.get(ident, 0), value)
                if len(scores) > limit * 2:
                    scores = dict(sorted(scores.items(), key=lambda row: row[1], reverse=True)[:limit])
        return dict(sorted(scores.items(), key=lambda row: row[1], reverse=True)[:limit])
    except Exception:
        return {}


def fact_scores(query, rows):
    encoder = get_encoder()
    if encoder is None or not rows or not query.strip():
        return {}
    try:
        import numpy as np
        texts = [row['text'] for row in rows]
        with _lock:
            epoch = _fact_epoch
            missing = list(dict.fromkeys(text for text in texts if text not in _fact_cache))
        if missing:
            vectors = encoder.encode(missing)
            with _lock:
                if epoch != _fact_epoch:
                    return {}
                for text, vector in zip(missing, vectors):
                    _fact_cache[text] = vector
                while len(_fact_cache) > 512:
                    _fact_cache.popitem(last=False)
        query_vector = encoder.encode([query], query=True)[0]
        with _lock:
            vectors = [_fact_cache.get(text) for text in texts]
        result = {}
        for row, vector in zip(rows, vectors):
            if vector is not None:
                score = float(np.dot(query_vector, vector))
                if np.isfinite(score) and score >= MIN_SIMILARITY:
                    result[row['id']] = score
        return result
    except Exception:
        return {}


def clear_fact_cache():
    global _fact_epoch
    with _lock:
        _fact_epoch += 1
        _fact_cache.clear()
