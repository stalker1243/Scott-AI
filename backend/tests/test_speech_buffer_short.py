"""A short initial buffer must keep PCM order, cancellation and saved choices."""
import json
from types import SimpleNamespace

import pytest
import voice_config
from speech_buffer import SpeechBuffer
from scott_voice_process import VoiceProcessError
from test_speech_buffer import audio,pcm
from test_voice_streaming import sink
from test_scott_voice_engine import integrated

pytestmark=pytest.mark.unit

def test_one_second_threshold_then_continuation_is_released_immediately():
    buffer=SpeechBuffer('1s')
    first=SimpleNamespace(seconds=.6); second=SimpleNamespace(seconds=.4); tail=SimpleNamespace(seconds=.1)
    assert buffer.push(first,False)==[]
    assert buffer.push(second,False)==[first,second]
    assert buffer.push(tail,True)==[tail]
    with pytest.raises(ValueError):buffer.push(tail,True)

@pytest.mark.parametrize('seconds',[.04,.7,.999])
def test_short_final_audio_is_never_kept_waiting_for_more(seconds):
    buffer=SpeechBuffer('1s'); block=SimpleNamespace(seconds=seconds)
    assert buffer.push(block,True)==[block]

def test_saved_short_buffer_preserves_all_other_preferences():
    voice_config.CONFIG_PATH.write_text(json.dumps(dict(voice='scott-voice',scott_profile='scott',
        scott_streaming=False,scott_acceleration=True,other='keep')),encoding='utf8')
    voice_config.save_voice('scott-voice',buffer_mode='1s')
    assert voice_config.get_scott_buffer()=='1s'
    assert voice_config.get_scott_profile()=='scott' and voice_config.get_scott_acceleration()
    assert not voice_config.get_scott_streaming()
    assert json.loads(voice_config.CONFIG_PATH.read_text())['other']=='keep'

def test_stream_sink_keeps_every_sample_and_removes_only_its_copy(sink,tmp_path):
    integrated,player=sink
    voice_config.save_voice('scott-voice',buffer_mode='1s')
    blocks=[audio(tmp_path,'one',.6,b'\x01\x00'),audio(tmp_path,'two',.4,b'\x02\x00'),audio(tmp_path,'tail',.1,b'\x03\x00')]
    received=[];paths=[]
    def play(path,**options):
        received.append(pcm(path));paths.append(path);return True
    player.play=player.play_and_wait=play
    def stream(text,profile,output,abort):
        for index,block in enumerate(blocks):
            output(block,index==2)
            assert len(received)==(0 if index==0 else index)
        return blocks[-1]
    integrated.clients[0].stream=stream
    assert integrated.voice.speak_stream('проверка')==blocks[-1].path
    assert received==[pcm(blocks[0].path)+pcm(blocks[1].path),pcm(blocks[2].path)]
    assert not __import__('pathlib').Path(paths[0]).exists()
    assert all(__import__('pathlib').Path(block.path).is_file() for block in blocks)

def test_cancel_while_buffering_discards_pending_audio_without_fallback(sink,tmp_path,monkeypatch):
    integrated,player=sink
    voice_config.save_voice('scott-voice',buffer_mode='1s')
    block=audio(tmp_path,'pending',.6)
    def stream(text,profile,output,abort):
        output(block,False);assert player.calls==[]
        player.stop();output(block,True)
        pytest.fail('Late audio accepted after cancellation')
    integrated.clients[0].stream=stream
    monkeypatch.setattr(integrated.voice,'_speak_to_file_locked',lambda *args:pytest.fail('Cancelled audio retried'))
    assert integrated.voice.speak_stream('проверка') is None
    assert player.calls==[('stop',True)]
    assert not list(tmp_path.glob('.scott-playback-*'))

def test_failure_after_release_stops_without_replay(sink,tmp_path,monkeypatch):
    integrated,player=sink
    voice_config.save_voice('scott-voice',buffer_mode='1s')
    blocks=[audio(tmp_path,'one',.6),audio(tmp_path,'two',.4)]
    def stream(text,profile,output,abort):
        for block in blocks:output(block,False)
        assert len(player.calls)==1
        abort();raise VoiceProcessError('synthesis_failed')
    integrated.clients[0].stream=stream
    monkeypatch.setattr(integrated.voice,'_speak_to_file_locked',lambda *args:pytest.fail('Partial audio replayed'))
    assert integrated.voice.speak_stream('проверка') is None
    assert len([call for call in player.calls if call[0]!='stop'])==1

def test_failure_before_release_retains_existing_fallback(sink,tmp_path,monkeypatch):
    integrated,player=sink
    voice_config.save_voice('scott-voice',buffer_mode='1s')
    block=audio(tmp_path,'pending',.6);fallback=audio(tmp_path,'fallback',.7)
    def stream(text,profile,output,abort):
        output(block,False);assert player.calls==[]
        abort();raise VoiceProcessError('synthesis_failed')
    integrated.clients[0].stream=stream
    monkeypatch.setattr(integrated.voice,'_speak_to_file_locked',lambda *args:fallback.path)
    assert integrated.voice.speak_stream('проверка')==fallback.path
    assert player.calls==[(fallback.path,True)]

def test_short_buffer_cannot_build_an_unbounded_pending_queue():
    buffer=SpeechBuffer('1s')
    for _ in range(128):assert buffer.push(SimpleNamespace(seconds=.001),False)==[]
    with pytest.raises(ValueError,match='Excessive'):buffer.push(SimpleNamespace(seconds=.001),False)

def test_catalog_exposes_short_buffer_without_changing_current_choice(sink):
    import scott_voice
    voice_config.save_voice('scott-voice',buffer_mode='1s')
    catalog=scott_voice.describe_voices()
    assert catalog['scott_buffer']=='1s'
    assert [row['id'] for row in catalog['scott_buffers']]==['immediate','1s','2s','4s','complete']
    assert next(row for row in catalog['scott_buffers'] if row['id']=='1s')['title']=='1 секунда звука'
