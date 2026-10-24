"""Diagnose supply and driver interruptions without logging content or changing PCM."""
import json
import threading
import time
from types import SimpleNamespace
import numpy as np
import pytest
from scipy.io import wavfile
import performance_trace
import speech_player
from test_stream_playback import output

pytestmark=pytest.mark.unit

@pytest.fixture
def diagnostic_rows(monkeypatch):
    rows=[]
    monkeypatch.setattr(speech_player,'record_timing',lambda stage,seconds,ok=True,meta=None:
        rows.append(dict(stage=stage,seconds=seconds,ok=ok,meta=meta)),raising=False)
    return rows

def test_one_stream_summary_keeps_pcm_and_request_id(output,diagnostic_rows):
    player,device,_,paths=output;token=object()
    with performance_trace.session('voice',fresh=True) as trace:
        for path in paths[:-1]:assert player.play_stream(path,token)
        assert player.play_stream(paths[-1],token,last=True,timeout=3)
    assert len(diagnostic_rows)==1
    row=diagnostic_rows[0];meta=row['meta']
    assert row['stage']=='voice.audio_output' and row['ok']
    assert meta['request_id']==trace.id and meta['metric']=='audio_output'
    assert meta['mode']=='stream' and meta['blocks']==3 and meta['frames']==7200
    assert meta['underflow_blocks']==0 and not meta['aborted']
    expected=np.concatenate([wavfile.read(path)[1].astype(np.float32)/32768*.5 for path in paths])
    np.testing.assert_array_equal(np.concatenate(device.streams[0].pcm),expected)
    assert not any(value in json.dumps(row) for value in paths)

def test_supply_lateness_is_separate_from_driver_underflow(output,diagnostic_rows,monkeypatch):
    player,device,_,paths=output;token=object();clock=iter([10.,10.4])
    monkeypatch.setattr(speech_player,'time',SimpleNamespace(monotonic=lambda:next(clock),perf_counter=time.perf_counter))
    with performance_trace.session('voice',fresh=True):
        assert player.play_stream(paths[0],token)
        assert player.play_stream(paths[1],token,last=True,timeout=3)
    assert len(diagnostic_rows)==1
    meta=diagnostic_rows[0]['meta']
    assert meta['supply_gap_count']==1
    assert meta['max_supply_gap_ms']==pytest.approx(300,abs=.01)
    assert meta['underflow_blocks']==0 and device.streams[0].closes==1

def test_driver_underflow_is_reported_without_repeating_audio(output,diagnostic_rows):
    player,device,_,paths=output;device.underflow=True
    with performance_trace.session('voice',fresh=True):
        assert player.play_stream(paths[0],object(),last=True,timeout=3)
    assert len(diagnostic_rows)==1 and not diagnostic_rows[0]['ok']
    assert diagnostic_rows[0]['meta']['underflow_blocks']==1
    assert len(device.streams)==1 and len(device.streams[0].pcm)==1

def test_file_output_summary_contains_technical_data_only(output,diagnostic_rows):
    player,device,_,paths=output
    with performance_trace.session('voice',fresh=True) as trace:
        assert player.queue_file(paths[0]).result(3)
    assert len(diagnostic_rows)==1
    meta=diagnostic_rows[0]['meta']
    assert meta['request_id']==trace.id and meta['mode']=='file' and meta['frames']==2400
    assert 'underflow_blocks' not in meta and not meta['aborted']
    assert not any(value in json.dumps(meta) for value in paths)

def test_cancelled_stream_summary_is_marked_aborted_and_closed(output,diagnostic_rows):
    player,device,_,paths=output;device.block='write'
    with performance_trace.session('voice',fresh=True):ticket=player.queue_stream(paths[0],object(),last=False)
    assert device.entered.wait(2)
    player.stop();device.release.set()
    assert ticket.released.wait(2)
    assert player.queue_file(paths[-1]).result(3)
    assert len(diagnostic_rows)==1 and diagnostic_rows[0]['meta']['aborted']
    assert device.streams[0].closes==1

def test_diagnostic_failure_never_breaks_playback(output,monkeypatch):
    player,device,_,paths=output
    def broken(*args,**kwargs):raise OSError('Synthetic diagnostics failure')
    monkeypatch.setattr(speech_player,'record_timing',broken,raising=False)
    with performance_trace.session('voice',fresh=True):
        assert player.play_stream(paths[0],object(),last=True,timeout=3)
    assert len(device.streams[0].pcm)==1 and not player.busy

def test_no_extra_output_record_without_request_context(output,diagnostic_rows):
    player,_,_,paths=output
    assert player.play_stream(paths[0],object(),last=True,timeout=3)
    assert diagnostic_rows==[]

def analyzer():
    from test_performance_trace import analyzer as existing
    return existing()

def test_summary_separates_late_supply_from_underflow_and_discards_text(tmp_path):
    path=tmp_path/'timings.jsonl'
    base=dict(request_id='a'*12,metric='audio_output',mode='stream',frames=24000,rate=24000,blocks=2,
        aborted=False,underflow_blocks=0,supply_gap_count=1,max_supply_gap_ms=320.5,
        prompt='synthetic-secret-prompt',device_name='synthetic-private-device')
    rows=[dict(stage='voice.audio_output',ms=1000,ok=True,meta=base),
          dict(stage='voice.audio_output',ms=200,ok=False,meta=dict(base,underflow_blocks=1,supply_gap_count=0,max_supply_gap_ms=0)),
          dict(stage='voice.audio_output',ms=100,ok=True,meta=dict(metric='audio_output',mode='file',
              frames=2400,rate=24000,aborted=True))]
    path.write_text('\n'.join(map(json.dumps,rows)),encoding='utf8')
    result=analyzer().analyze(path);summary=result['playback']
    assert result['records']==3 and result['ignored']==0
    assert summary['stream_sessions']==2 and summary['file_sessions']==1 and summary['aborted_sessions']==1
    assert summary['driver_underflow_blocks']==1 and summary['supply_gap_count']==1
    assert summary['max_estimated_supply_gap_ms']==320.5
    assert result['stages'][0]['metric']=='audio_output'
    assert 'synthetic-' not in json.dumps(result)

@pytest.mark.parametrize('field,value',[('underflow_blocks',True),('blocks',-1),('max_supply_gap_ms',float('inf')),
    ('supply_gap_count','1'),('aborted','yes')])
def test_summary_rejects_malformed_audio_diagnostics(tmp_path,field,value):
    meta=dict(metric='audio_output',mode='stream',frames=2400,rate=24000,blocks=1,
        underflow_blocks=0,supply_gap_count=0,max_supply_gap_ms=0,aborted=False)
    meta[field]=value
    path=tmp_path/'timings.jsonl'
    path.write_text(json.dumps(dict(stage='voice.audio_output',ms=100,ok=True,meta=meta)),encoding='utf8')
    result=analyzer().analyze(path)
    assert result['records']==0 and result['ignored']==1 and result['playback']['sessions']==0

def test_summary_separates_inter_output_waits_for_each_request(tmp_path):
    rows=[]
    for ident,start,finish in [('a'*12,0,100),('b'*12,0,1000),('a'*12,500,600),('b'*12,1000,1100)]:
        rows.append(dict(stage='voice.audio_output',ms=finish-start,ok=True,
            meta=dict(request_id=ident,metric='audio_output',mode='file',frames=2400,rate=24000,
                aborted=False,started_ms=start,finished_ms=finish)))
    path=tmp_path/'timings.jsonl';path.write_text('\n'.join(map(json.dumps,rows)),encoding='utf8')
    summary=analyzer().analyze(path)['playback']
    assert summary['max_inter_output_gap_ms']==400
    assert summary['output'][2]['previous_output_gap_ms']==400
    assert summary['output'][3]['previous_output_gap_ms']==0
