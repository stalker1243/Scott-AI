"""Index integrity and hybrid recall, with small deterministic fake embeddings."""
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

import intelligent_answerer as ia
import memories
import semantic_memory as semantic

pytestmark = pytest.mark.unit


class FakeEncoder:
    def encode(self, texts, query=False):
        result = np.zeros((len(texts), semantic.DIMENSIONS), dtype='<f4')
        for n, text in enumerate(texts):
            topic = 0 if any(word in text for word in ('visual-design', 'surface-layout', 'Glass', 'Алексей')) else 1
            result[n, topic] = 1
        return result


def wait_index(archive):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = archive.semantic_status()
        if state['indexed_turns'] == state['total_turns']:
            return
        time.sleep(0.01)
    pytest.fail('Fake semantic index did not finish')


@pytest.fixture
def encoder(monkeypatch):
    fake = FakeEncoder()
    monkeypatch.setenv('SCOTT_SEMANTIC_MEMORY', '1')
    monkeypatch.setattr(semantic, '_encoder', fake)
    monkeypatch.setattr(semantic, '_state', 'ready')
    monkeypatch.setattr(semantic, '_retry_after', 0)
    monkeypatch.setattr(semantic, '_jobs', {})
    monkeypatch.setattr(semantic, '_index_errors', {})
    monkeypatch.setattr(semantic, '_fact_cache', semantic.OrderedDict())
    monkeypatch.setattr(semantic, 'load', lambda **kwargs: fake)
    yield fake
    deadline = time.monotonic() + 5
    while semantic._jobs and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not semantic._jobs


def memory(tmp_path):
    return ia.ConversationMemory(max_history=4, context_file=tmp_path / 'chat.jsonl')


def test_semantic_recall_without_shared_words_survives_restart(tmp_path, encoder):
    original = memory(tmp_path)
    original.record_external_turn('visual-design', 'Glass')
    for n in range(15):
        original.record_external_turn(f'arithmetic-{n}', str(n))
    wait_index(original.archive)
    restored = memory(tmp_path)
    assert any('Glass' in row['content'] for row in restored.recall('surface-layout'))
    assert restored.archive.semantic_status()['indexed_turns'] == 16


def test_deleted_fact_is_not_returned_through_semantic_matches(tmp_path, encoder):
    current = memory(tmp_path)
    memories.observe('Меня зовут Алексей')
    current.record_external_turn('Меня зовут Алексей', 'Алексей, готово')
    wait_index(current.archive)
    assert memories.remove(memories.all_memories()[0]['id'])['success']
    assert current.recall('surface-layout') == []


def test_clear_removes_vectors_and_markers_atomically(tmp_path, encoder, monkeypatch):
    current = memory(tmp_path)
    current.record_external_turn('visual-design', 'Glass')
    wait_index(current.archive)
    with monkeypatch.context() as readonly:
        readonly.setattr(ia, 'atomic_write_text', lambda *a: (_ for _ in ()).throw(OSError('read-only')))
        with pytest.raises(OSError):
            current.clear()
    assert current.archive.semantic_status()['indexed_turns'] == 1
    with current.archive.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM semantic_chunks').fetchone()[0] == 2
    current.clear()
    with current.archive.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM semantic_chunks').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM semantic_turns').fetchone()[0] == 0


def test_clearing_during_indexing_cannot_attach_old_vectors_to_reused_id(tmp_path, encoder, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    actual_encode = encoder.encode
    def blocked(texts, query=False):
        if 'visual-design' in texts:
            entered.set()
            assert release.wait(5)
        return actual_encode(texts, query=query)
    monkeypatch.setattr(encoder, 'encode', blocked)
    current = memory(tmp_path)
    current.record_external_turn('visual-design', 'Glass')
    assert entered.wait(5)
    current.clear()
    current.record_external_turn('arithmetic', '42')
    release.set()
    wait_index(current.archive)
    assert current.archive.count() == 1
    assert current.recall('surface-layout') == []
    with current.archive.connection() as db:
        vectors = db.execute('SELECT vector FROM semantic_chunks').fetchall()
    assert vectors and all(np.frombuffer(row[0], dtype='<f4')[1] == 1 for row in vectors)


def test_corrupt_or_different_model_vectors_are_ignored(tmp_path, encoder):
    current = memory(tmp_path)
    current.record_external_turn('arithmetic', '42')
    wait_index(current.archive)
    with current.archive.connection() as db:
        db.execute('UPDATE semantic_chunks SET vector=?', (b'bad',))
        db.execute('INSERT INTO semantic_chunks VALUES(?,?,?,?,?)',
                   (1, 3, 'another-model', 0, encoder.encode(['visual-design'])[0].tobytes()))
    assert semantic.candidates(current.archive, 'surface-layout') == {}
    assert current.archive.recall('arithmetic')  # Keyword fallback remains available.


def test_encoder_failure_keeps_original_history_and_keyword_recall(tmp_path, encoder, monkeypatch):
    monkeypatch.setattr(encoder, 'encode', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('inference failed')))
    current = memory(tmp_path)
    current.record_external_turn('visual-design', 'Glass')
    deadline = time.monotonic() + 5
    while semantic._jobs and time.monotonic() < deadline:
        time.sleep(0.01)
    assert current.archive.count() == 1
    assert any('Glass' in row['content'] for row in current.archive.recall('visual-design'))
    assert current.archive.semantic_status()['state'] == 'unavailable'


def test_semantic_facts_rank_older_topic_and_deletion_clears_cache(encoder, monkeypatch):
    memories.add('visual-design Glass')
    for n in range(12):
        memories.add(f'arithmetic {n}')
    monkeypatch.setattr(memories, 'MAX_IN_PROMPT', 2)
    assert 'Glass' in memories.prompt_addition('surface-layout')
    assert semantic._fact_cache
    row = next(row for row in memories.all_memories() if 'Glass' in row['text'])
    memories.remove(row['id'])
    assert not semantic._fact_cache
    assert 'Glass' not in memories.prompt_addition('surface-layout')


def test_missing_model_sets_cooldown_without_failing_keyword_memory(monkeypatch, tmp_path):
    monkeypatch.setenv('SCOTT_SEMANTIC_MEMORY', '1')
    monkeypatch.setattr(semantic, '_encoder', None)
    monkeypatch.setattr(semantic, '_retry_after', 0)
    monkeypatch.setattr(semantic, '_state', 'not_loaded')
    calls = []
    def missing(**kwargs):
        calls.append(kwargs)
        raise ImportError('onnxruntime missing')
    monkeypatch.setattr(semantic, 'Encoder', missing)
    assert semantic.load() is None
    assert semantic.load() is None
    assert len(calls) == 1 and semantic.status()['state'] == 'unavailable'


def test_deleting_fact_during_encoding_does_not_repopulate_cache(encoder, monkeypatch):
    memories.add('visual-design Glass')
    rows = memories.all_memories()
    entered, release = threading.Event(), threading.Event()
    encode = encoder.encode
    def blocked(texts, query=False):
        if any('visual-design' in text for text in texts):
            entered.set()
            assert release.wait(5)
        return encode(texts, query=query)
    monkeypatch.setattr(encoder, 'encode', blocked)
    results = []
    worker = threading.Thread(target=lambda: results.append(semantic.fact_scores('surface-layout', rows)))
    worker.start()
    assert entered.wait(5)
    memories.remove(rows[0]['id'])
    release.set()
    worker.join(5)
    assert not worker.is_alive()
    assert results == [{}] and not semantic._fact_cache


def test_mean_pooling_ignores_padding_and_applies_retrieval_prefixes():
    seen = []
    def tokenize(texts):
        seen.extend(texts)
        return [SimpleNamespace(ids=[2, 1], attention_mask=[1, 0], type_ids=[0, 0]) for _ in texts]
    def run(outputs, feed):
        values = np.zeros((len(feed['input_ids']), 2, semantic.DIMENSIONS), dtype=np.float32)
        values[:, 0, 0] = 2
        values[:, 1, 1] = 1000
        return [values]
    instance = semantic.Encoder.__new__(semantic.Encoder)
    instance.tokenizer = SimpleNamespace(encode_batch=tokenize)
    instance.session = SimpleNamespace(run=run)
    instance.inputs = {'input_ids', 'attention_mask'}
    instance.lock = threading.Lock()
    assert instance.encode(['question'], query=True)[0, 0] == 1
    assert instance.encode(['document'])[0, 1] == 0
    assert seen == ['query: question', 'passage: document']
