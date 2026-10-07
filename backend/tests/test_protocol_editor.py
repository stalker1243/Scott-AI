"""Editor mutations and tracked runs use isolated files and fake executors."""
import asyncio
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import protocol_endpoints as endpoints
from protocol_jobs import ProtocolJobs
from protocols import ProtocolStore, run_async

pytestmark = pytest.mark.unit


def test_update_is_atomic_and_preserves_identity(tmp_path, monkeypatch):
    store = ProtocolStore(tmp_path / "protocols.json")
    before = store.add("A / B", ["one", "two"], schedule="по будням в 09:00")["protocol"]
    store.add("Other", ["other"])
    assert not store.update("A / B", name="Other", steps=["changed"])["success"]
    assert not store.update("A / B", steps=["changed"], schedule="invalid")["success"]
    assert store.get("A / B").to_dict() == before
    monkeypatch.setattr(store, "_write", lambda items: (_ for _ in ()).throw(OSError("disk failure")))
    assert not store.update_by_id(before["id"], name="New")["success"]
    assert not store.delete_by_id(before["id"])["success"]
    assert not store.add("New", ["step"])["success"]
    assert store.get("A / B").to_dict() == before
    assert ProtocolStore(store.path).get("A / B").to_dict() == before


@pytest.mark.asyncio
async def test_repeat_skip_continue_and_progress(tmp_path):
    store = ProtocolStore(tmp_path / "protocols.json")
    saved = store.add("Wide", [{"text": "one"}, {"text": "skip", "enabled": False}, {"text": "fail", "pause": 2}],
                      repeat_count=2, stop_on_error=False)
    assert saved["success"]
    protocol = ProtocolStore(store.path).get("Wide")
    called, pauses, events = [], [], []
    async def execute(text):
        called.append(text)
        return {"success": text != "fail", "response": "result"}
    async def sleep(seconds): pauses.append(seconds)
    result = await run_async(protocol, execute, sleep=sleep, progress=events.append)
    assert called == ["one", "fail", "one", "fail"] and pauses == [2, 2]
    assert not result.ok and result.total == 4 and result.stopped_at is None
    assert [s.iteration for s in result.steps] == [1, 1, 2, 2]
    assert events[-1]["current"] == 4 and "ошибками" in result.summary()
    assert not store.update("Wide", steps=[{"text": "off", "enabled": False}])["success"]
    assert not store.update("Wide", repeat_count=21)["success"]


@pytest.mark.asyncio
async def test_jobs_cancel_pause_and_do_not_mutate_started_sequence(tmp_path):
    store = ProtocolStore(tmp_path / "protocols.json")
    store.add("Run", [{"text": "one", "pause": 10}, {"text": "two"}])
    called = []
    started = asyncio.Event()
    async def runner(protocol, progress=None):
        async def execute(text): called.append(text); started.set(); return "done"
        return await run_async(protocol, execute, sleep=asyncio.sleep, progress=progress)
    jobs = ProtocolJobs()
    job = jobs.start(store.get("Run"), runner)["job"]
    await started.wait()
    assert not jobs.start(store.get("Run"), runner)["success"]
    assert jobs.get(job["id"])["steps"][0]["ok"]
    assert jobs.cancel(job["id"])["success"]
    await asyncio.sleep(0); await asyncio.sleep(0)
    assert jobs.get(job["id"])["state"] == "cancelled" and called == ["one"]
    # Immediate cancellation, before the coroutine enters its try block.
    job = jobs.start(store.get("Run"), runner)["job"]
    jobs.cancel(job["id"])
    await asyncio.sleep(0); await asyncio.sleep(0)
    assert jobs.get(job["id"])["state"] == "cancelled"


@pytest.mark.asyncio
async def test_id_endpoints_and_result(tmp_path, monkeypatch):
    store = ProtocolStore(tmp_path / "protocols.json")
    monkeypatch.setattr(endpoints.scott_runtime, "protocols", store)
    monkeypatch.setattr(endpoints, "jobs", ProtocolJobs())
    calls = []
    async def runner(protocol, progress=None):
        async def execute(text): calls.append(text); return "done"
        result = await run_async(protocol, execute, progress=progress)
        if result.ok: store.mark_run(protocol)
        return result
    monkeypatch.setattr(endpoints.scott_runtime, "run_protocol", runner)
    app = FastAPI(); app.include_router(endpoints.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = (await client.post("/protocols", json={"name": "A / B? #", "steps": ["first"], "repeat_count": 2})).json()
        protocol_id = result["protocol"]["id"]
        result = (await client.patch(f"/protocols/id/{protocol_id}", json={"name": "Renamed / &", "steps": ["edited"]})).json()
        assert result["success"] and result["protocol"]["repeat_count"] == 2 and not calls
        result = (await client.post(f"/protocols/id/{protocol_id}/start")).json()
        for _ in range(20):
            await asyncio.sleep(0)
            if endpoints.jobs.current().get("state") != "running":
                break
        job = (await client.get("/protocols/jobs/current")).json()["job"]
        assert job["state"] == "completed" and calls == ["edited", "edited"]
        assert store.get_by_id(protocol_id).runs == 1
        assert (await client.delete(f"/protocols/id/{protocol_id}")).json()["success"]


@pytest.mark.asyncio
async def test_zero_pause_commands_yield_for_cancel(tmp_path):
    store = ProtocolStore(tmp_path / "protocols.json")
    store.add("Fast", ["one", "two", "three"])
    jobs = ProtocolJobs(); calls = []
    async def runner(protocol, progress=None):
        async def execute(text):
            calls.append(text)
            if len(calls) == 1:
                asyncio.get_running_loop().call_soon(jobs.cancel, jobs.current()["id"])
            return "done"
        return await run_async(protocol, execute, progress=progress)
    jobs.start(store.get("Fast"), runner)
    for _ in range(8): await asyncio.sleep(0)
    assert calls == ["one"] and jobs.current()["state"] == "cancelled"


@pytest.mark.asyncio
async def test_assistant_serializes_top_level_runs_and_keeps_nested_depth(main_module, tmp_path, monkeypatch):
    store = ProtocolStore(tmp_path / "protocols.json")
    store.add("Simple", ["step"])
    store.add("Recursive", ["nested"])
    monkeypatch.setattr(main_module.scott_runtime, "protocols", store)
    assistant = object.__new__(type(main_module.scott_ai))
    active = 0; maximum = 0
    async def execute(text, quiet_mode=True):
        nonlocal active, maximum
        if text == "nested":
            result = await assistant.run_protocol(store.get("Recursive"), depth=main_module._protocol_depth_context.get())
            return {"success": result.ok, "response": result.summary()}
        active += 1; maximum = max(maximum, active)
        await asyncio.sleep(0.01)
        active -= 1
        return "done"
    assistant._process_command_impl = execute
    first, second = await asyncio.gather(assistant.run_protocol(store.get("Simple")), assistant.run_protocol(store.get("Simple")))
    assert first.ok and second.ok and maximum == 1 and store.get("Simple").runs == 2
    result = await assistant.run_protocol(store.get("Recursive"))
    assert not result.ok and main_module._protocol_depth_context.get() == 0
    assert store.get("Recursive").runs == 0
