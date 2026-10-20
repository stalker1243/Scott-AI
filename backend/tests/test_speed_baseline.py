"""Controlled waits, not an API/GPU benchmark. Kept identical before/after."""
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import pytest
from backend.tests.test_chats import setup, create, routes

pytestmark = pytest.mark.unit

def test_controlled_provider_parallelism(setup, monkeypatch):
    setup.ia._state_lock = lambda: lock
    lock = threading.RLock()
    def complete(*args):
        time.sleep(.12)
        return 'controlled answer'
    monkeypatch.setattr(routes, 'complete', complete)
    chats = [create(setup) for _ in range(3)]
    start = time.perf_counter()
    with ThreadPoolExecutor(3) as workers:
        results = list(workers.map(lambda chat: setup.client.post(f'/chats/{chat}/messages',data={'question':'controlled question'}),chats))
    assert all(row.status_code == 200 for row in results)
    assert all(len(setup.db.get(chat)['messages']) == 2 for chat in chats)
    print(f'SPEED_JSON {{"case":"three_chats_120ms_provider","elapsed_ms":{(time.perf_counter()-start)*1000:.3f}}}')

def test_fact_observation_without_facts(monkeypatch):
    from backend import memories
    def settings():
        time.sleep(.015)
        return {'auto_capture':True}
    monkeypatch.setattr(memories, 'settings', settings)
    start = time.perf_counter()
    for _ in range(12):
        assert memories.observe('Открой тестовое приложение') == []
    print(f'SPEED_JSON {{"case":"twelve_nonfacts_15ms_settings","elapsed_ms":{(time.perf_counter()-start)*1000:.3f}}}')
