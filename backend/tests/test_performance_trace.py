"""Correlated measurements must not change cancellation, audio or installation behavior."""
import asyncio
import importlib.util
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import zipfile
import pytest

import performance_trace as trace
import request_flow
import timing

pytestmark=pytest.mark.unit

@pytest.fixture
def records(monkeypatch,tmp_path):
    timing.reset()
    monkeypatch.setattr(timing,'LOG_DIR',tmp_path)
    monkeypatch.setattr(timing,'_LOG_PATH',tmp_path/'timings.jsonl')
    monkeypatch.setattr(timing,'LOG_ENABLED',True)
    def read():
        path=tmp_path/'timings.jsonl'
        return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []
    return read

def test_one_voice_id_includes_recognition_before_async_dispatch(records):
    async def check():
        loop=asyncio.get_running_loop()
        async def response():
            flow=request_flow.Flow(kind='voice')
            flow.emit('Synthetic fixture reply')
            flow.mark('total')
            return flow.id
        def microphone_thread():
            with trace.session('voice',started=time.perf_counter()-.1,fresh=True) as session:
                with trace.phase('voice.recognition'):
                    pass
                return session.id,asyncio.run_coroutine_threadsafe(response(),loop)
        ident,future=await asyncio.to_thread(microphone_thread)
        assert await asyncio.wrap_future(future)==ident
        rows=records()
        assert {row['meta']['request_id'] for row in rows}=={ident}
        assert next(row['ms'] for row in rows if row['stage']=='voice.first_text')>=100
        assert trace.current() is None
    asyncio.run(check())

def test_nested_setup_phases_copy_safe_id_without_mutating_environment(records,monkeypatch):
    monkeypatch.setenv('SCOTT_TRACE_ID','private text is not an id')
    with trace.session('setup') as session:
        with trace.phase('setup.pip_install') as outcome:
            outcome.ok=False
        env={'KEEP':'value'}
        child=trace.environment(env)
        assert child['SCOTT_TRACE_ID']==session.id and env=={'KEEP':'value'}
        assert child['SCOTT_TRACE_ID']!='private text is not an id'
    assert records()[0]['ok'] is False
    assert trace.current() is None

def test_child_provisioning_reuses_parent_id(records,monkeypatch):
    monkeypatch.setenv('SCOTT_TRACE_ID','a'*12)
    with trace.session('voice_setup') as session:
        assert session.id=='a'*12
    with trace.session('voice',fresh=True) as voice:
        assert voice.id!='a'*12

@pytest.mark.parametrize('error',[RuntimeError('fixture'),asyncio.CancelledError()])
def test_failed_and_cancelled_phases_are_recorded_and_reraised(records,error):
    with pytest.raises(type(error)):
        with trace.phase('setup.fixture'):
            raise error
    assert records()[0]['ok'] is False
    assert trace.current() is None

def test_false_step_is_not_logged_as_a_success(records):
    @trace.measured('setup.total',success=lambda result:result.done)
    def operation():return SimpleNamespace(done=False,error='private fixture text')
    assert not operation().done
    assert records()[0]['ok'] is False and 'private' not in json.dumps(records())

@pytest.mark.parametrize('models_ready',[True,False])
def test_ready_dependencies_checked_once_and_preserved_when_models_missing(monkeypatch,models_ready):
    import bootstrap
    calls=[]
    monkeypatch.setattr(bootstrap,'dependencies_ready',lambda *a:calls.append('dependencies') or True)
    monkeypatch.setattr(bootstrap,'_models_ready_for',lambda *a:models_ready)
    monkeypatch.setattr(bootstrap,'install_dependencies',lambda *a:pytest.fail('Ready libraries must be preserved'))
    monkeypatch.setattr(bootstrap,'download_models',lambda *a:calls.append('models') or bootstrap.Step('fixture',done=True))
    assert bootstrap.prepare().done
    assert calls==(['dependencies'] if models_ready else ['dependencies','models'])

def test_logging_failure_does_not_break_work(monkeypatch,tmp_path):
    target=tmp_path/'not-a-directory';target.write_text('preserve')
    monkeypatch.setattr(timing,'LOG_DIR',target)
    monkeypatch.setattr(timing,'_LOG_PATH',target/'timings.jsonl')
    @trace.measured('setup.total')
    def operation():return 'same result'
    assert operation()=='same result' and target.read_text()=='preserve'

def test_logs_rotate_and_old_records_remain_exportable(records,monkeypatch):
    monkeypatch.setattr(timing,'LOG_LIMIT',1)
    for name in ('setup.first','setup.second','setup.third'):
        timing.record(name,.1)
    parent=timing._LOG_PATH.parent
    assert json.loads((parent/'timings.jsonl.2').read_text())['stage']=='setup.first'
    assert json.loads((parent/'timings.jsonl.1').read_text())['stage']=='setup.second'
    assert records()[0]['stage']=='setup.third'

def test_first_audio_submission_requires_actual_successful_device_call(records,monkeypatch):
    import numpy as np
    import speech_player as player
    monkeypatch.setattr(player,'PLAYBACK_AVAILABLE',True)
    monkeypatch.setattr(player,'_audio_settings',lambda:None)
    monkeypatch.setattr(player.SpeechPlayer,'_read_audio',staticmethod(lambda path:(24000,np.zeros(2400,dtype='float32'))))
    monkeypatch.setattr(player.SpeechPlayer,'_echo_reference',staticmethod(lambda:SimpleNamespace(start=lambda *a:None,stop=lambda:None)))
    calls=[]
    monkeypatch.setattr(player.sd,'play',lambda *a,**k:calls.append('submitted'))
    monkeypatch.setattr(player.sd,'wait',lambda:None)
    instance=player.SpeechPlayer()
    try:
        with trace.session('voice',fresh=True):
            for _ in range(2):
                assert instance.queue_file('synthetic.wav').result(2)
        assert calls==['submitted','submitted']
        assert len([row for row in records() if row['stage']=='voice.first_audio_submitted'])==1
        before=len(records())
        monkeypatch.setattr(player,'_muted',lambda:True)
        with trace.session('voice',fresh=True):assert instance.queue_file('muted.wav') is None
        assert len(records())==before
    finally:
        instance.stop();instance._queue.put(None);instance._worker.join(2)

def analyzer():
    path=Path(__file__).resolve().parents[2]/'tools/analyze_timings.py'
    spec=importlib.util.spec_from_file_location('timing_analyzer_fixture',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def test_support_zip_summary_ignores_secrets_and_keeps_milestones_separate(tmp_path):
    rows=[dict(stage='voice.first_text',ms=12,ok=True,meta=dict(request_id='b'*12,prompt='private prompt',token='private token')),
          dict(stage='voice.recognition',ms=8,ok=True,meta=dict(request_id='b'*12,metric='duration')),
          dict(stage='../private',ms=1,ok=True),dict(stage='setup.total',ms=float('nan'),ok=True)]
    path=tmp_path/'support.zip'
    with zipfile.ZipFile(path,'w') as archive:
        archive.writestr('logs/timings.jsonl','\n'.join(map(json.dumps,rows))+'\ninvalid unfinished row')
        archive.writestr('api-errors.log','private token')
    result=analyzer().analyze(path)
    assert result['records']==2 and result['ignored']==3
    assert {row['metric'] for row in result['stages']}=={'duration','milestone'}
    assert result['requests'][0]['milestones_ms']=={'voice.first_text':12}
    assert 'private' not in json.dumps(result)
