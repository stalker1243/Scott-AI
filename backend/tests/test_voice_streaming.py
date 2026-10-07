"""Synthetic protocol, stateful DSP and playback cancellation; no devices or models."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import time
import wave

import numpy as np
import pytest

from scott_voice_process import ScottVoiceProcess,VoiceProcessError,stream_path
from test_scott_voice_process import config
from test_scott_voice_engine import integrated, wav
from types import SimpleNamespace

pytestmark=pytest.mark.unit
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'experiments/voice_design'))
from stream_voice import ColourStream,StreamVolume
from create_scott_voice import colour_voice


STREAM_WORKER='''
import argparse,json,sys,time,wave,os
from pathlib import Path
from scott_voice_process import PROTOCOL,VoiceProcessConfig,recipe_id,publish_audio,watch_owner,stream_path,checksum
watch_owner()
p=argparse.ArgumentParser();p.add_argument('--configuration');a=p.parse_args()
c=VoiceProcessConfig.from_wire(json.loads(a.configuration))
def emit(value): print(json.dumps(value),flush=True)
def wav(path,frames):
    with wave.open(str(path),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(b'\\x40\\x01'*frames)
emit(dict(event='ready',protocol=PROTOCOL,recipe=recipe_id(c),features=['stream_v1']))
for line in sys.stdin:
    r=json.loads(line); req=r['id']; text=r['text']; n=0
    if r['action']=='stream':
        count=128 if text=='очередь' else 40 if text=='таймаут' else 3
        for i in range(count):
            part=stream_path(c.cache_dir,req,i); wav(part,2400)
            emit(dict(event='chunk',id=req,key=r['key'],sequence=i+1 if text=='порядок' else i,
                last=i==count-1 and text not in ('конец','таймаут'),sha256='bad' if text=='хеш' else checksum(part)))
            n+=2400
            if text=='сбой': os._exit(17)
            if text!='очередь': time.sleep(.025)
    else: n=7200
    temporary=c.cache_dir/f'.pending-{req}.wav';wav(temporary,n+1 if text=='длина' else n)
    publish_audio(c.cache_dir,r['key'],req,temporary)
    emit(dict(event='audio',id=req,key=r['key'],cached=False))
'''


@pytest.fixture
def streaming(config):
    config.worker.write_text(STREAM_WORKER,encoding='utf-8')
    return config


def test_stream_callbacks_are_ordered_files_are_live_and_cache_is_complete(streaming):
    seen=[]
    def output(audio,last):
        assert Path(audio.path).is_file()
        seen.append((audio.seconds,last,audio.cached))
    with ScottVoiceProcess(streaming) as client:
        result=client.stream('поток','natural',output)
        assert seen==[(.1,False,False),(.1,False,False),(.1,True,False)]
        assert result.seconds==.3 and not result.cached
        assert not list(streaming.cache_dir.glob('.stream-*'))
        client.cancel(); seen.clear()
        hit=client.stream('поток','natural',output)
        assert hit.cached and seen==[(.3,True,True)] and not client.status()['running']


@pytest.mark.parametrize('text,code',[('порядок','invalid_protocol'),('хеш','invalid_audio'),
                                    ('конец','invalid_protocol'),('длина','invalid_audio')])
def test_bad_stream_is_stopped_before_partial_files_are_removed(streaming,text,code):
    aborted=[]
    def abort():
        assert list(streaming.cache_dir.glob('.stream-*'))
        aborted.append(True)
    with ScottVoiceProcess(streaming) as client:
        with pytest.raises(VoiceProcessError,match=code):
            client.stream(text,'natural',lambda *args:None,abort)
        assert not client.status()['running']
        assert not list(streaming.cache_dir.glob('.stream-*'))
        if text not in ('порядок','хеш'):
            assert aborted==[True]


def test_stream_cancellation_never_delivers_the_tail(streaming):
    seen=[]
    with ScottVoiceProcess(streaming) as client:
        def output(audio,last):
            seen.append(last);client.cancel()
        with pytest.raises(VoiceProcessError,match='cancelled'):
            client.stream('поток','natural',output)
        assert seen==[False] and not client.status()['running']
        assert not list(streaming.cache_dir.glob('.stream-*'))


def test_fast_cached_profile_burst_does_not_overflow_reader_queue(streaming):
    seen=[]
    def output(audio,last):
        time.sleep(.005)
        seen.append(last)
    with ScottVoiceProcess(streaming) as client:
        result=client.stream('очередь','natural',output)
        assert result.seconds==12.8 and seen==[False]*127+[True]


def test_cancellation_during_complete_cache_callback_is_observed(streaming):
    with ScottVoiceProcess(streaming) as client:
        client.synthesize('кеш','natural')
        with pytest.raises(VoiceProcessError,match='cancelled'):
            client.stream('кеш','natural',lambda *args:client.cancel())


def test_stream_progress_does_not_extend_the_total_model_budget(streaming):
    with ScottVoiceProcess(streaming,timeout=.15,startup_timeout=3) as client:
        with pytest.raises(VoiceProcessError,match='timeout'):
            client.stream('таймаут','natural',lambda *args:None)
        assert not client.status()['running']


def test_playback_wait_is_not_counted_as_model_synthesis_time(streaming):
    with ScottVoiceProcess(streaming,timeout=.4,startup_timeout=3) as client:
        result=client.stream('поток','natural',lambda *args:time.sleep(.2))
        assert result.path


def test_failed_sink_aborts_output_and_worker(streaming):
    aborted=[]
    def fail(*args): raise RuntimeError('synthetic sink failure')
    with ScottVoiceProcess(streaming) as client:
        with pytest.raises(VoiceProcessError):
            client.stream('поток','natural',fail,lambda:aborted.append(True))
        assert aborted==[True] and not client.status()['running']
        assert not list(streaming.cache_dir.glob('.stream-*'))


def test_old_worker_remains_usable_for_complete_wav(config):
    with ScottVoiceProcess(config) as client:
        with pytest.raises(VoiceProcessError,match='stream_unavailable'):
            client.stream('поток','natural',lambda *args:None)
        assert client.synthesize('обычный','natural').path


@pytest.mark.parametrize('sequence',[-1,128,True,'1'])
def test_stream_identity_rejects_invalid_sequence(sequence,tmp_path):
    with pytest.raises(VoiceProcessError): stream_path(tmp_path,'0'*32,sequence)


@pytest.mark.parametrize('mix',[.16,.32,.52])
def test_digital_colour_matches_full_processor_across_arbitrary_boundaries(mix):
    rate=24000
    signal=(.06*np.sin(np.arange(18000)*.2)+.02*np.cos(np.arange(18000)*.7)).astype(np.float32)
    profile=dict(carrier_hz=72,body_mix=mix,presence=.1,delay_ms=5.1,resonance=.07)
    stream=ColourStream(rate,profile)
    # Include a block shorter than the resonance delay to catch state loss.
    pieces=np.split(signal,[1,80,7200,12345])
    result=np.concatenate([stream.process(piece) for piece in pieces])
    np.testing.assert_allclose(result,colour_voice(signal,rate,profile),atol=1e-7,rtol=1e-6)


def test_stream_gain_is_fixed_after_first_speech_and_preserves_silence():
    volume=StreamVolume()
    assert not volume.process(np.zeros(200)).any() and volume.gain is None
    volume.process(np.ones(200)*.02)
    gain=volume.gain
    assert not volume.process(np.zeros(200)).any() and volume.gain==gain
    loud=volume.process(np.ones(200))
    assert volume.gain==gain and loud.max()<=.951


@pytest.mark.parametrize('values',[[],[float('nan')],[[.1,.2]]])
def test_bad_pcm_never_reaches_stream_callback(values):
    with pytest.raises(ValueError): StreamVolume().process(values)


@pytest.fixture
def sink(integrated,monkeypatch):
    import audio_settings, speech_player, voice_config
    voice_config.save_voice('eugene')
    voice_config.save_voice('scott-voice',streaming=True)
    player=SimpleNamespace(generation=0,calls=[])
    player.play=lambda path,**options:player.calls.append((path,False)) or True
    player.play_and_wait=lambda path,**options:player.calls.append((path,True)) or True
    def stop(generation=None):
        if generation is None or generation==player.generation:
            player.generation+=1;player.calls.append(('stop',True))
    player.stop=stop
    monkeypatch.setattr(speech_player,'get_player',lambda:player)
    monkeypatch.setattr(audio_settings,'is_quiet',lambda:False)
    integrated.engine.synthesize('init')
    return integrated,player


def test_speech_sink_queues_blocks_once_and_waits_for_tail(sink):
    integrated,player=sink
    path=integrated.engine.synthesize('fixture')
    def stream(text,profile,output,abort):
        output(SimpleNamespace(path=path),False)
        output(SimpleNamespace(path=path),True)
        return SimpleNamespace(path=path)
    integrated.clients[0].stream=stream
    assert integrated.voice.speak_stream('поток')==path
    assert player.calls==[(path,False),(path,True)]


def test_partial_stream_failure_stops_output_without_replaying_or_fallback(sink,monkeypatch):
    integrated,player=sink
    path=integrated.engine.synthesize('fixture')
    def stream(text,profile,output,abort):
        output(SimpleNamespace(path=path),False)
        raise VoiceProcessError('synthesis_failed')
    integrated.clients[0].stream=stream
    monkeypatch.setattr(integrated.voice,'_speak_to_file_locked',lambda *args:pytest.fail('partial speech replayed'))
    assert integrated.voice.speak_stream('поток') is None
    assert player.calls==[(path,False),('stop',True)]


def test_stream_falls_back_to_full_scott_before_any_audio_if_worker_is_old(sink):
    integrated,player=sink
    assert integrated.voice.speak_stream('поток')
    assert len(player.calls)==1 and player.calls[0][1] is True


def test_voice_streaming_is_opt_in_and_persists_independently(monkeypatch):
    import voice_config
    voice_config.CONFIG_PATH.write_text('{}')
    assert not voice_config.get_scott_streaming()
    voice_config.save_voice('scott-voice',streaming=True)
    voice_config.save_voice('eugene')
    voice_config.save_voice('scott-voice',profile='digital')
    assert voice_config.get_scott_streaming() and voice_config.get_scott_profile()=='digital'


def test_voice_route_validates_streaming_and_keeps_preferences_on_failure(main_module,integrated,monkeypatch):
    import asyncio,httpx,voice_config
    monkeypatch.setattr(integrated.engine,'describe',lambda:dict(available=True,streaming_available=True))
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main_module.app),base_url='http://test') as client:
            assert (await client.post('/voice/select',json={'voice':'scott-voice','streaming':True})).status_code==200
            assert voice_config.get_scott_streaming()
            for voice,value in [('scott-voice',1),('scott-voice',None),('scott-voice','true'),('eugene',True)]:
                assert (await client.post('/voice/select',json={'voice':voice,'streaming':value})).status_code==400
            monkeypatch.setattr(integrated.engine,'describe',lambda:dict(available=True,streaming_available=False))
            assert (await client.post('/voice/select',json={'voice':'scott-voice','streaming':True})).status_code==503
            assert voice_config.get_scott_streaming()
            assert (await client.post('/voice/select',json={'voice':'scott-voice','streaming':False})).status_code==200
            assert not voice_config.get_scott_streaming()
    asyncio.run(run())


@pytest.mark.parametrize('cancel',[False,True])
def test_voice_reply_uses_stream_once_and_keeps_interruption_guard(main_module,integrated,monkeypatch,cancel):
    import asyncio,audio_settings,runtime,voice_config
    voice_config.save_voice('scott-voice',streaming=True)
    text='Проверка потокового ответа и сохранения всех слов ' * 10
    spoken=[];echo=[]
    def stream(chunk):
        assert echo==['start']
        spoken.append(chunk)
        if cancel: main_module._next_voice_response()
        return 'complete.wav'
    def duplicate(*args,**kwargs): pytest.fail('Stream reply replayed as a complete WAV')
    monkeypatch.setattr(runtime,'scott_voice',SimpleNamespace(speak_stream=stream,
        speak_to_file=duplicate,play_audio=duplicate))
    monkeypatch.setattr(runtime,'listener',SimpleNamespace(expect_interruption=lambda _:echo.append('start'),
        stop_expecting=lambda:echo.append('stop')))
    monkeypatch.setattr(audio_settings,'is_quiet',lambda:False)
    generation=main_module._next_voice_response()
    assert asyncio.run(main_module._play_voice_response(text,generation)) is (not cancel)
    assert echo==['start','stop']
    if cancel: assert len(spoken)==1
    else: assert ' '.join(spoken).split()==text.split()
