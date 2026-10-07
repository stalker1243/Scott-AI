"""Search must not stop health polling. All providers and audio are fake."""

import asyncio
import threading
import time
from types import SimpleNamespace

import httpx
import pytest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("route", ["question", "llm", "web", "search"])
def test_health_responds_while_search_is_waiting(main_module, monkeypatch, route):
    main = main_module
    started = threading.Event()
    release = threading.Event()

    def slow_result(*args, **kwargs):
        started.set()
        # A rescue timeout makes the regression fail without hanging pytest.
        release.wait(0.8)
        return "Тестовый ответ"

    monkeypatch.setattr(main, "HAS_V32_FEATURES", False)
    monkeypatch.setattr(main, "knowledge_base", SimpleNamespace(
        search_memory=lambda _: {}, add_conversation=lambda *args: None))
    parsed = SimpleNamespace(command_type="search", main_param="тест", context={})
    decision = SimpleNamespace(kind="question" if route == "llm" else route if route != "search" else "command",
                               service="github", query="тест", parsed=parsed, action="search", reason="test")
    monkeypatch.setattr(main.understanding, "understand", lambda *args, **kwargs: decision)
    monkeypatch.setattr(main.question_answerer, "answer", slow_result)
    if route == "llm":
        monkeypatch.setattr(main.question_answerer, "answer", lambda *args, **kwargs: None)
        monkeypatch.setattr(main, "intelligent_answerer", SimpleNamespace(answer_question=slow_result, model="test"))
    monkeypatch.setattr(main.web_integrations, "search_github_repo",
                        lambda _: {"message": slow_result()})
    monkeypatch.setattr(main.executor, "execute", lambda *args, **kwargs: slow_result())
    monkeypatch.setattr(main, "web_scraper", None)

    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://localhost") as client:
            begin = time.monotonic()
            command = asyncio.create_task(main.scott_ai.process_command("Тест поиска", by_voice=True))
            try:
                while not started.is_set():
                    await asyncio.sleep(0.005)
                health = await client.get("/health")
                elapsed = time.monotonic() - begin
                assert health.status_code == 200
                assert health.json()["status"] == "online"
                assert elapsed < 0.4, f"/health blocked for {elapsed:.2f}s during {route}"
                assert not command.done(), "Health only responded after search finished"
            finally:
                release.set()
                await command

    asyncio.run(check())


@pytest.fixture
def voice_runtime(main_module, monkeypatch):
    import audio_settings
    main = main_module
    monkeypatch.setattr(audio_settings, "is_quiet", lambda: False)
    monkeypatch.setattr(main, "THINKING_CUE_AFTER_SECONDS", 10)
    played = []
    synthesized = []
    expecting = []
    stats = SimpleNamespace(last_dispatch="выполнена", last_error="", last_answer_seconds=0)
    listener = SimpleNamespace(stats=stats, _answered_at=0,
                               expect_interruption=lambda text: expecting.append(text),
                               stop_expecting=lambda: expecting.append(None))
    voice = SimpleNamespace(speak_to_file=lambda text: synthesized.append(text) or text,
                            play_audio=lambda path: played.append(path))
    monkeypatch.setattr(main.scott_runtime, "listener", listener)
    monkeypatch.setattr(main.scott_runtime, "scott_voice", voice)
    return main, listener, voice, played, synthesized, expecting


def test_new_question_suppresses_old_voice_reply(voice_runtime, monkeypatch):
    main, listener, voice, played, synthesized, expecting = voice_runtime

    async def check():
        monkeypatch.setattr(main, "_main_loop", asyncio.get_running_loop())
        waiting = asyncio.Event()
        release = asyncio.Event()

        async def command(text, **kwargs):
            if text == "старый":
                waiting.set()
                await release.wait()
            return {"response": text}

        monkeypatch.setattr(main.scott_ai, "process_command", command)
        old = main._listener_handle("старый")
        await waiting.wait()
        new = main._listener_handle("новый")
        try:
            await asyncio.wrap_future(new)
        finally:
            release.set()
            await asyncio.wrap_future(old)
        assert played == ["новый"]
        assert synthesized == ["новый"]
        assert expecting == ["новый", None]
        assert listener._answered_at > 0

    asyncio.run(check())


def test_stop_during_synthesis_prevents_playback(voice_runtime, monkeypatch):
    import speech_player
    main, listener, voice, played, _, expecting = voice_runtime
    started = threading.Event()
    release = threading.Event()
    stopped = []
    monkeypatch.setattr(speech_player, "PLAYBACK_AVAILABLE", True)
    monkeypatch.setattr(speech_player, "get_player", lambda: SimpleNamespace(stop=lambda: stopped.append(True)))

    def synthesize(text):
        started.set()
        release.wait(2)
        return text

    voice.speak_to_file = synthesize

    async def check():
        generation = main._next_voice_response()
        reply = asyncio.create_task(main._play_voice_response("Ответ", generation))
        try:
            assert await asyncio.to_thread(started.wait, 1)
            main._listener_interrupted("стоп")
        finally:
            release.set()
        assert not await reply
        assert played == []
        assert expecting == []
        assert stopped == [True]

    asyncio.run(check())


def test_quiet_voice_reply_does_not_synthesize(voice_runtime, monkeypatch):
    import audio_settings
    main, _, _, played, synthesized, expecting = voice_runtime
    monkeypatch.setattr(audio_settings, "is_quiet", lambda: True)
    assert not asyncio.run(main._play_voice_response("Тест"))
    assert synthesized == played == expecting == []


def test_voice_failure_is_reported_in_listener_state(voice_runtime, monkeypatch):
    main, listener, _, _, _, _ = voice_runtime

    async def check():
        monkeypatch.setattr(main, "_main_loop", asyncio.get_running_loop())

        async def command(*args, **kwargs):
            raise RuntimeError("test command failure")

        monkeypatch.setattr(main.scott_ai, "process_command", command)
        with pytest.raises(RuntimeError):
            await asyncio.wrap_future(main._listener_handle("Тест"))
        assert listener.stats.last_dispatch == "ошибка"
        assert "test command failure" in listener.stats.last_error

    asyncio.run(check())


def test_thinking_cue_runs_while_command_is_pending(voice_runtime, monkeypatch):
    main, _, _, played, _, _ = voice_runtime
    monkeypatch.setattr(main, "THINKING_CUE_AFTER_SECONDS", 0.01)

    async def check():
        monkeypatch.setattr(main, "_main_loop", asyncio.get_running_loop())
        release = asyncio.Event()

        async def command(*args, **kwargs):
            await release.wait()
            return {"response": "Готово"}

        monkeypatch.setattr(main.scott_ai, "process_command", command)
        task = main._listener_handle("Тест")
        try:
            async with asyncio.timeout(1):
                while not played:
                    await asyncio.sleep(0.005)
            assert played[0] in main.THINKING_CUES
            assert not task.done()
            assert (await main.health())["status"] == "online"
        finally:
            release.set()
            await asyncio.wrap_future(task)
        assert played[-1] == "Готово"

    asyncio.run(check())


def test_concurrent_first_recognition_loads_one_model(main_module, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    main = main_module
    started = threading.Event()
    release = threading.Event()
    loads = []

    class Recognizer:
        device = "cpu"

        def __init__(self, *args):
            loads.append(True)

        def load(self):
            started.set()
            release.wait(2)

    monkeypatch.setattr(main.stt_engine, "Recognizer", Recognizer)
    monkeypatch.setattr(main, "_resolve_whisper_device", lambda: "cpu")
    monkeypatch.setattr(main, "_whisper_model_cache", None)
    monkeypatch.setattr(main, "_whisper_device", None)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(main._get_whisper_model)
        try:
            assert started.wait(1)
            second = pool.submit(main._get_whisper_model)
        finally:
            release.set()
        assert first.result() is second.result()
    assert loads == [True]
