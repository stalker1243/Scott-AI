"""Restart, concurrent requests and failed writes must preserve memory."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

import intelligent_answerer as ia
import memories
import storage

pytestmark = pytest.mark.unit


def test_clear_survives_restart(tmp_path):
    path = tmp_path / "conversation.jsonl"
    memory = ia.ConversationMemory(context_file=path)
    memory.add_message("user", "Вопрос")
    memory.add_message("assistant", "Ответ")
    assert ia.ConversationMemory(context_file=path).get_context() == memory.get_context()
    memory.clear()
    assert memory.get_context() == []
    assert ia.ConversationMemory(context_file=path).get_context() == []


def test_unanswered_question_is_not_persisted(tmp_path):
    path = tmp_path / "conversation.jsonl"
    memory = ia.ConversationMemory(context_file=path)
    memory.add_message("user", "Первый")
    memory.add_message("assistant", "Первый ответ")
    memory.add_message("user", "Неудачный")
    memory.drop_unanswered()
    assert [row["content"] for row in ia.ConversationMemory(context_file=path).get_context()] == ["Первый", "Первый ответ"]


def test_corrupt_lines_and_old_incomplete_turns_do_not_hide_history(tmp_path):
    path = tmp_path / "conversation.jsonl"
    messages = [
        {"role": "assistant", "content": "Сирота"},
        {"role": "user", "content": "Неудачный"},
        {"role": "user", "content": "Вопрос"},
        {"role": "assistant", "content": "Ответ"},
        {"role": "user", "content": "Без ответа"},
    ]
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in messages[:3]) +
                    "\n{broken\n42\n" + "\n".join(json.dumps(row, ensure_ascii=False) for row in messages[3:]), encoding="utf-8")
    assert ia.ConversationMemory(context_file=path).get_context() == [
        {"role": "user", "content": "Вопрос"}, {"role": "assistant", "content": "Ответ"}]


def test_context_and_disk_keep_bounded_complete_turns(tmp_path):
    path = tmp_path / "conversation.jsonl"
    memory = ia.ConversationMemory(max_history=5, context_file=path)
    for n in range(30):
        memory.add_message("user", f"Вопрос {n}")
        memory.add_message("assistant", f"Ответ {n}")
    context = memory.get_context()
    assert [row["role"] for row in context] == ["user", "assistant", "user", "assistant"]
    assert context[-1]["content"] == "Ответ 29"
    assert len(path.read_text(encoding="utf-8").splitlines()) == len(context)
    assert ia.ConversationMemory(max_history=5, context_file=path).get_context() == context


def test_failed_clear_preserves_disk_and_ram(tmp_path, monkeypatch):
    path = tmp_path / "conversation.jsonl"
    memory = ia.ConversationMemory(context_file=path)
    memory.add_message("user", "Вопрос")
    memory.add_message("assistant", "Ответ")
    before = path.read_bytes()
    context = memory.get_context()
    monkeypatch.setattr(storage.os, "replace", lambda *args: (_ for _ in ()).throw(OSError("disk failure")))
    with pytest.raises(OSError):
        memory.clear()
    assert path.read_bytes() == before
    assert memory.get_context() == context
    assert not list(tmp_path.glob("*.tmp"))


def test_concurrent_llm_turns_cannot_mix_questions(tmp_path):
    started = threading.Event()
    release = threading.Event()
    second_started = threading.Event()
    sent = []

    def create(**kwargs):
        sent.append(kwargs["messages"])
        question = kwargs["messages"][-1]["content"]
        if question == "Первый":
            started.set()
            release.wait(2)
        else:
            second_started.set()
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=f"Ответ: {question}"))])

    answerer = ia.IntelligentAnswerer.__new__(ia.IntelligentAnswerer)
    answerer.enabled = True
    answerer.api_provider = "OpenAI"
    answerer.model = "fake"
    answerer.temperature = 0.3
    answerer.max_tokens = 100
    answerer.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    answerer.memory = ia.ConversationMemory(context_file=tmp_path / "conversation.jsonl")
    answerer.retry_pending_connection = lambda: False
    answerer.instructions = lambda brief, query='': "test"

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(answerer.answer, "Первый")
        try:
            assert started.wait(1)
            second = pool.submit(answerer.answer, "Второй")
            assert not second_started.wait(0.05)
        finally:
            release.set()
        assert first.result()[1]
        assert second.result()[1]
    assert [row["content"] for row in answerer.memory.get_context()] == [
        "Первый", "Ответ: Первый", "Второй", "Ответ: Второй"]
    assert sent[1][-3:] == answerer.memory.get_context()[:-1]


def test_concurrent_fact_additions_are_not_lost(tmp_path, monkeypatch):
    monkeypatch.setattr(memories, "STORE_PATH", tmp_path / "memories.json")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda n: memories.add(f"Факт {n}"), range(20)))
    assert all(result["success"] for result in results)
    assert len(memories.all_memories()) == 20


def test_failed_fact_write_preserves_old_file(tmp_path, monkeypatch):
    path = tmp_path / "memories.json"
    monkeypatch.setattr(memories, "STORE_PATH", path)
    assert memories.add("Первый")["success"]
    before = path.read_bytes()
    monkeypatch.setattr(storage.os, "replace", lambda *args: (_ for _ in ()).throw(OSError("disk failure")))
    assert not memories.add("Второй")["success"]
    assert path.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


def test_corrupt_fact_store_is_not_overwritten_on_add(tmp_path, monkeypatch):
    path = tmp_path / "memories.json"
    monkeypatch.setattr(memories, "STORE_PATH", path)
    path.write_text("{broken", encoding="utf-8")
    assert memories.all_memories() == []
    assert not memories.add("Новый факт")["success"]
    assert path.read_text(encoding="utf-8") == "{broken"
