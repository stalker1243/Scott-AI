"""Readiness and known local replies must not wait for optional stock speech."""
import asyncio
import threading
from types import SimpleNamespace

import pytest

pytestmark=pytest.mark.unit

def test_startup_does_not_generate_stock_audio(main_module,monkeypatch):
    import speech_cache
    calls=[]
    warmed=[]
    monkeypatch.setattr(main_module,'_warmup_whisper_sync',lambda:warmed.append(True))
    monkeypatch.setattr(speech_cache,'warm',lambda **kwargs:calls.append(kwargs) or dict(total=0))
    asyncio.run(main_module._warmup_models())
    assert warmed==[True]
    assert calls==[], 'Startup speech generation competes with explicitly requested voice preparation'


def test_failed_recognition_warmup_does_not_start_optional_voice(main_module,monkeypatch):
    import speech_cache
    calls=[]
    def fail():raise RuntimeError('Fixture recognizer unavailable')
    monkeypatch.setattr(main_module,'_warmup_whisper_sync',fail)
    monkeypatch.setattr(speech_cache,'warm',lambda **kwargs:calls.append(kwargs) or dict(total=0))
    asyncio.run(main_module._warmup_models())
    assert calls==[], 'A recognition failure must not start unrelated GPU synthesis'


def test_cancelled_recognition_warmup_does_not_start_optional_voice(main_module,monkeypatch):
    import speech_cache
    main=main_module
    entered=threading.Event()
    release=threading.Event()
    calls=[]
    def warm():
        entered.set()
        assert release.wait(3)
    monkeypatch.setattr(main,'_warmup_whisper_sync',warm)
    monkeypatch.setattr(speech_cache,'warm',lambda **kwargs:calls.append(kwargs) or dict(total=0))
    async def check():
        task=asyncio.create_task(main._warmup_models())
        try:
            assert await asyncio.to_thread(entered.wait,2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
            assert calls==[]
        finally:
            release.set()
            await asyncio.gather(task,return_exceptions=True)
    asyncio.run(check())

def test_optional_voice_does_not_synthesize_a_thinking_cue(main_module,monkeypatch):
    import scott_voice
    main=main_module
    monkeypatch.setattr(scott_voice,'get_current_voice',lambda:'scott-voice')
    monkeypatch.setattr(main.scott_runtime,'scott_voice',object())
    monkeypatch.setattr(main,'_voice_response_current',lambda generation:True)
    calls=[]
    async def play(*args):calls.append(args)
    monkeypatch.setattr(main,'_play_voice_response',play)
    asyncio.run(main._say_thinking())
    assert calls==[], 'A filler phrase must not start the optional speech model'

def test_completed_local_reply_starts_before_archive_finishes(main_module,monkeypatch):
    import voice_flow
    main=main_module
    entered,release=threading.Event(),threading.Event()
    def archive(*args):
        entered.set()
        assert release.wait(4)
    monkeypatch.setattr(main,'intelligent_answerer',SimpleNamespace(memory=SimpleNamespace(record_external_turn=archive)))
    monkeypatch.setattr(main,'HAS_V32_FEATURES',False)
    monkeypatch.setattr(main.memories_module,'observe',lambda text:[])
    async def command(*args,**kwargs):return dict(type='command',response='Готово.')
    monkeypatch.setattr(main.scott_ai,'_process_command_impl',command)
    async def check():
        spoken=[]
        audible=asyncio.Event()
        async def play(text):
            spoken.append(text)
            audible.set()
            return True
        async def cue():pytest.fail('Completed local reply must not need a thinking cue')
        task=asyncio.create_task(voice_flow.respond(
            lambda:main.scott_ai.process_command('Синтетический тест',by_voice=True),
            play,lambda:True,lambda text:text,cue,10))
        try:
            assert await asyncio.to_thread(entered.wait,2)
            await asyncio.wait_for(audible.wait(),1)
        finally:
            release.set()
            await task
        assert spoken==['Готово.']
    asyncio.run(check())
