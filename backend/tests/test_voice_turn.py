"""One voice turn keeps order, bounded prefetch, cancellation and echo guards."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
from types import SimpleNamespace

import pytest
import audio_settings
import request_flow
import scott_voice_engine
import voice_config
import voice_flow
from scott_voice_process import VoiceProcessError
from test_speech_pipeline import pipeline,output,integrated,folders,call_in_thread

pytestmark=pytest.mark.unit

def parts():
    assert hasattr(voice_flow,'_SpeechParts'),'Owned speech parts are absent'
    return voice_flow._SpeechParts()

@pytest.mark.parametrize('value',[None,'','  ',5,[],{},'x'*65537],
    ids=['none','empty','blank','number','list','dict','oversize'])
def test_invalid_text_never_enters_owned_queue(value):
    source=parts()
    with pytest.raises(ValueError):source.offer(value)
    source.finish()
    assert list(source)==[]

def test_two_parts_keep_order_and_third_is_rejected():
    source=parts()
    assert source.offer('первая') and source.offer('вторая')
    with pytest.raises(ValueError):source.offer('третья')
    source.finish()
    assert not source.offer('поздняя')
    assert list(source)==['первая','вторая']
    with pytest.raises(ValueError):list(source)

@pytest.mark.parametrize('action',['finish','cancel'])
def test_waiting_consumer_wakes_when_turn_ends(action):
    source=parts();entered=threading.Event()
    def read():
        entered.set()
        return list(source)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(read)
        assert entered.wait(1)
        getattr(source,action)()
        assert future.result(1)==[]

def test_cancel_drops_pending_text_and_observer():
    source=parts();seen=[]
    source.observe(seen.append)
    source.offer('первая');source.cancel()
    assert not source.offer('вторая') and list(source)==[] and seen==['первая']

def test_observer_replays_first_text_before_any_consumer_and_runs_on_owner():
    source=parts();owner=threading.get_ident();seen=[]
    source.offer('первая')
    source.observe(lambda text:seen.append((text,threading.get_ident())))
    source.offer('вторая');source.finish()
    assert seen==[('первая',owner),('вторая',owner)]
    assert list(source)==['первая','вторая']
    with pytest.raises(ValueError):source.observe(lambda text:None)

def test_current_guard_cancels_while_waiting_for_continuation():
    source=parts();entered=threading.Event();cancelled=threading.Event()
    def current():
        entered.set()
        if cancelled.is_set():raise VoiceProcessError('cancelled')
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(lambda:list(source.consume(current)))
        assert entered.wait(1)
        cancelled.set()
        with pytest.raises(VoiceProcessError,match='cancelled'):future.result(1)

def test_continuation_is_offered_while_opening_playback_is_still_blocked():
    parts()  # Baseline must fail on the missing behavior, not an unexpected kwarg.
    async def run():
        first,second,release=asyncio.Event(),asyncio.Event(),asyncio.Event()
        seen=[];flows=[]
        async def consume(source):
            flow=request_flow.current();assert flow is not None
            flows.append(flow)
            def read():
                for text in source:
                    seen.append(text)
                    loop.call_soon_threadsafe(first.set if len(seen)==1 else second.set)
            loop=asyncio.get_running_loop()
            await asyncio.to_thread(read)
            await release.wait()
            return True
        async def produce():
            flow=request_flow.current()
            await asyncio.to_thread(flow.emit,'Первая законченная фраза. Вторая')
            await asyncio.wait_for(first.wait(),1)
            await asyncio.to_thread(flow.emit,' законченная фраза.')
            return dict(response='Первая законченная фраза. Вторая законченная фраза.')
        async def old_play(text):pytest.fail('Turn fell back to serial playback')
        async def cue():pytest.fail('Turn unexpectedly needed a cue')
        task=asyncio.create_task(voice_flow.respond(produce,old_play,lambda:True,lambda x:x,cue,10,play_parts=consume))
        try:
            await asyncio.wait_for(second.wait(),1)
            assert not task.done() and len(flows)==1
            assert seen==['Первая законченная фраза.','Вторая законченная фраза.']
        finally:
            release.set();await task
    asyncio.run(run())

def test_completed_local_reply_uses_existing_playback_before_archive_returns():
    parts()
    async def run():
        spoken=asyncio.Event();release=asyncio.Event();seen=[]
        async def play(text):
            seen.append(text);spoken.set();return True
        async def produce():
            response=dict(type='command',response='Готово.')
            await asyncio.to_thread(request_flow.current().ready_response,response)
            await release.wait()
            return response
        async def fail(*a):pytest.fail('Completed reply entered a waiting text queue')
        task=asyncio.create_task(voice_flow.respond(produce,play,lambda:True,lambda x:x,fail,10,play_parts=fail))
        try:
            await asyncio.wait_for(spoken.wait(),1)
            assert seen==['Готово.'] and not task.done()
        finally:
            release.set();await task
    asyncio.run(run())

@pytest.mark.parametrize('result,expected',[
    ('Первая законченная фраза. Остаток ответа.',['Первая законченная фраза.','Остаток ответа.']),
    ('Совсем другой ответ.',['Первая законченная фраза.']),
    ('❌ Соединение прервалось.',['Первая законченная фраза.','Ответ прервался. Попробуйте задать вопрос ещё раз.'])])
def test_prefix_is_never_replayed_or_replaced(result,expected):
    parts()
    async def run():
        seen=[];started=asyncio.Event()
        async def consume(source):
            started.set()
            await asyncio.to_thread(lambda:seen.extend(source))
            return True
        async def produce():
            await asyncio.to_thread(request_flow.current().emit,'Первая законченная фраза. Начало')
            await asyncio.wait_for(started.wait(),1)
            return dict(response=result)
        async def fail(*a):pytest.fail('Unexpected legacy/cue call')
        response=await voice_flow.respond(produce,fail,lambda:True,lambda x:x,fail,10,play_parts=consume)
        assert response['response']==result and seen==expected
    asyncio.run(run())

@pytest.mark.parametrize('cause',['generation','producer_error','task_cancel'])
def test_failed_or_superseded_producer_closes_waiting_consumer(cause):
    parts()
    async def run():
        started=asyncio.Event();closed=threading.Event();valid=[True];hold=asyncio.Event()
        loop=asyncio.get_running_loop()
        async def consume(source):
            def read():
                loop.call_soon_threadsafe(started.set)
                try:
                    for _ in source:pass
                finally:closed.set()
            await asyncio.to_thread(read)
            return True
        async def produce():
            await asyncio.to_thread(request_flow.current().emit,'Первая законченная фраза. Начало')
            await started.wait()
            if cause=='producer_error':raise RuntimeError('Synthetic model failure')
            if cause=='generation':valid[0]=False
            else:await hold.wait()
            return dict(response='Первая законченная фраза. Остаток.')
        async def fail(*a):pytest.fail('Unexpected legacy/cue call')
        task=asyncio.create_task(voice_flow.respond(produce,fail,lambda:valid[0],lambda x:x,fail,10,play_parts=consume))
        await asyncio.wait_for(started.wait(),1)
        if cause=='task_cancel':task.cancel()
        if cause in ('producer_error','task_cancel'):
            with pytest.raises(RuntimeError if cause=='producer_error' else asyncio.CancelledError):await task
        else:await task
        assert await asyncio.to_thread(closed.wait,1)
    asyncio.run(run())

@pytest.mark.parametrize('streaming',[True,False])
def test_turn_prepares_continuation_before_opening_drain(pipeline,monkeypatch,streaming):
    source=parts();state=pipeline
    release=threading.Event();entered=threading.Event()
    if streaming:
        state.device.block='stop'
        entered=state.device.entered;release=state.device.release
    else:
        def wait():entered.set();assert release.wait(3)
        state.device.wait=wait
        def synth(text,*args):
            state.requests.append(text)
            if len(state.requests)==2:state.second.set()
            return state.paths[0]
        monkeypatch.setattr(state.voice,'_speak_to_file_locked',synth)
    source.offer('первая')
    thread,result=call_in_thread(lambda:state.voice.speak_turn(source,streaming=streaming))
    try:
        assert entered.wait(2)
        source.offer('вторая');source.finish()
        assert state.second.wait(2),'Continuation synthesis waited for opening playback'
        assert state.requests==['первая','вторая'] and thread.is_alive()
    finally:release.set()
    thread.join(3)
    assert result and result[0] and not thread.is_alive() and not folders(state)

@pytest.mark.parametrize('cause',['caller','quiet','engine','player'])
def test_waiting_for_next_text_does_not_block_a_new_command(pipeline,monkeypatch,cause):
    source=parts();state=pipeline;cancelled=threading.Event();quiet=[False]
    monkeypatch.setattr(audio_settings,'is_quiet',lambda:quiet[0])
    entered=threading.Event();original_wait=source._condition.wait
    def wait(timeout):
        entered.set()
        return original_wait(timeout)
    source._condition.wait=wait
    source.offer('первая')
    thread,result=call_in_thread(lambda:state.voice.speak_turn(source,streaming=True,cancelled=cancelled.is_set))
    assert entered.wait(2)
    # No second text arrives. Invalidating any owner must wake the waiter.
    if cause=='caller':cancelled.set()
    elif cause=='quiet':quiet[0]=True
    elif cause=='engine':state.engine.cancel()
    else:state.player.stop()
    thread.join(2)
    assert result==[None] and not thread.is_alive()
    source.cancel()
    assert not folders(state)

def test_echo_continuation_preserves_calibration_and_end_clears_it():
    parts()
    from listener import VoiceListener
    instance=VoiceListener(transcribe=lambda audio:'',handle_command=lambda text:None)
    instance.expect_interruption('Первая фраза.')
    instance._playback_level=.25;instance._playback_blocks=17
    instance.extend_interruption('Продолжение ответа.')
    assert instance._speaking_text=='первая фраза. продолжение ответа.'
    assert instance._playback_level==.25 and instance._playback_blocks==17
    instance.stop_expecting();instance.extend_interruption('Устаревшая фраза')
    assert not instance._speaking_text and not instance.is_expecting_interruption

def test_main_turn_keeps_one_echo_session_and_request_context(main_module,monkeypatch):
    source=parts();main=main_module
    assert hasattr(main,'_play_voice_turn')
    events=[];loop_thread=threading.get_ident()
    class Listener:
        stats=SimpleNamespace(last_error='')
        def expect_interruption(self,text):events.append(('start',text,threading.get_ident()))
        def extend_interruption(self,text):events.append(('extend',text,threading.get_ident()))
        def stop_expecting(self):events.append(('stop','',threading.get_ident()))
    def consume(turn,**options):
        assert request_flow.current() is not None
        assert options['streaming'] is False
        return 'owned.wav' if list(turn)==['первая','вторая'] else None
    monkeypatch.setattr(main.scott_runtime,'listener',Listener())
    monkeypatch.setattr(main.scott_runtime,'scott_voice',SimpleNamespace(speak_turn=consume))
    monkeypatch.setattr(audio_settings,'is_quiet',lambda:False)
    voice_config.save_voice('scott-voice',streaming=False)
    source.offer('первая');source.offer('вторая');source.finish()
    async def run():
        with request_flow.use(request_flow.Flow(kind='voice')):
            assert await main._play_voice_turn(source)
    asyncio.run(run())
    assert events==[('start','первая',loop_thread),('extend','вторая',loop_thread),('stop','',loop_thread)]

@pytest.mark.parametrize('kind',['quiet','stale','missing'])
def test_main_unavailable_turn_never_synthesizes_or_starts_echo(main_module,monkeypatch,kind):
    source=parts();main=main_module
    assert hasattr(main,'_play_voice_turn')
    calls=[]
    monkeypatch.setattr(main.scott_runtime,'scott_voice',None if kind=='missing' else SimpleNamespace(speak_turn=lambda *a,**k:calls.append(True)))
    monkeypatch.setattr(audio_settings,'is_quiet',lambda:kind=='quiet')
    monkeypatch.setattr(main,'_voice_response_current',lambda generation:kind!='stale')
    source.offer('первая');source.finish()
    assert asyncio.run(main._play_voice_turn(source)) is False
    assert not calls and list(source)==[]
