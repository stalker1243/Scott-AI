"""Exercise real worker-process failures without loading Qwen or user data."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import time
import wave
import psutil

import pytest

from scott_voice_process import ScottVoiceProcess,VoiceProcessConfig,VoiceProcessError

pytestmark = pytest.mark.unit

FAKE_WORKER = '''
import argparse,json,os,sys,time,wave,subprocess
from pathlib import Path
from scott_voice_process import PROTOCOL,VoiceProcessConfig,recipe_id,publish_audio,watch_owner
watch_owner()
p=argparse.ArgumentParser();p.add_argument('--configuration');args=p.parse_args()
c=VoiceProcessConfig.from_wire(json.loads(args.configuration))
def emit(v):
    print(json.dumps(v),flush=True)
if os.environ.get('SCOTT_TEST_API_KEY'):
    (c.cache_dir/'secret-leaked').touch()
print('A library import writes to stderr',file=sys.stderr,flush=True)
(c.cache_dir/'worker-pid').write_text(str(os.getpid()))
emit(dict(event='ready',protocol=PROTOCOL,recipe=recipe_id(c),features=['prepare_v1']))
for line in sys.stdin:
    packet=json.loads(line); request=packet['id']
    if packet['action']=='prepare':
        (c.cache_dir/'preparing').touch()
        mode=os.environ.get('SCOTT_TEST_PREPARE_MODE','')
        if mode=='wait': time.sleep(20)
        if mode=='exit': os._exit(17)
        emit(dict(event='prepared',id='0'*32 if mode=='bad_id' else request,
            recipe='bad' if mode=='bad_recipe' else recipe_id(c)))
        continue
    temporary=c.cache_dir/f'.pending-{request}.wav'
    temporary.write_bytes(b'partial')
    if packet['text'] in ('таймаут','отмена'):
        time.sleep(20)
    if packet['text']=='дочерний':
        child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(20)'])
        (c.cache_dir/'child-pid').write_text(str(child.pid))
        child.wait()
    if packet['text']=='сбой':
        os._exit(17)
    time.sleep(.025)
    with wave.open(str(temporary),'wb') as output:
        output.setnchannels(1);output.setsampwidth(2);output.setframerate(24000)
        output.writeframes(b'\\x40\\x01'*2400)
    publish_audio(c.cache_dir,packet['key'],request,temporary)
    emit(dict(event='audio',id=request,key=packet['key'],cached=False))
'''


@pytest.fixture
def config(tmp_path):
    model = tmp_path/'model'
    model.mkdir()
    (model/'scott-model.json').write_text(json.dumps(dict(model='test-model',revision='test-revision')))
    reference = tmp_path/'reference'
    reference.mkdir()
    audio = reference/'scott-reference.wav'
    with wave.open(str(audio),'wb') as output:
        output.setnchannels(1);output.setsampwidth(2);output.setframerate(24000)
        output.writeframes(b'\x40\x01'*240)
    ref_json = reference/'reference.json'
    ref_json.write_text(json.dumps(dict(sha256=hashlib.sha256(audio.read_bytes()).hexdigest())))
    profiles = tmp_path/'profiles.json'
    profiles.write_text('[]')
    worker = tmp_path/'worker.py'
    worker.write_text(FAKE_WORKER,encoding='utf-8')
    return VoiceProcessConfig(Path(sys.executable),worker,model,ref_json,profiles,tmp_path/'cache')


def wait_for(predicate):
    deadline = time.monotonic()+3
    while time.monotonic()<deadline:
        if predicate():
            return
        time.sleep(.01)
    raise AssertionError('Worker did not reach the expected state')


def test_client_import_does_not_load_torch():
    result = subprocess.run([sys.executable,'-c',
         'import scott_voice_process,sys; assert "torch" not in sys.modules'],capture_output=True,text=True,timeout=5)
    assert result.returncode==0,result.stderr


def test_prepare_does_not_create_audio_and_reuses_worker(config):
    with ScottVoiceProcess(config) as voice:
        assert not voice.status()['model_loaded']
        assert voice.prepare()['model_loaded']
        assert voice.status()['active'] is False
        pid = voice.status()['pid']
        voice.prepare()
        assert voice.status()['pid']==pid
        assert not list(config.cache_dir.glob('*.wav'))
        assert not list(config.cache_dir.glob('*.json'))
        voice.synthesize('Проверка.')
        assert voice.status()['pid']==pid
        voice.cancel()
        assert not voice.status()['model_loaded']


@pytest.mark.parametrize('mode,code', [('wait','timeout'), ('exit','worker_exited'),
    ('bad_id','invalid_protocol'), ('bad_recipe','invalid_protocol')])
def test_prepare_failure_disposes_worker_and_can_retry(config, monkeypatch, mode, code):
    monkeypatch.setenv('SCOTT_TEST_PREPARE_MODE',mode)
    with ScottVoiceProcess(config,prepare_timeout=.2) as voice:
        with pytest.raises(VoiceProcessError) as error:
            voice.prepare()
        assert error.value.code==code and not voice.status()['running']
        monkeypatch.delenv('SCOTT_TEST_PREPARE_MODE')
        assert voice.prepare()['model_loaded']


def test_prepare_cancel_and_idle_release_do_not_leave_loaded_state(config, monkeypatch):
    monkeypatch.setenv('SCOTT_TEST_PREPARE_MODE','wait')
    with ScottVoiceProcess(config,idle_timeout=.1) as voice:
        with ThreadPoolExecutor(max_workers=1) as pool:
            request=pool.submit(voice.prepare)
            wait_for(lambda:(config.cache_dir/'preparing').exists())
            voice.cancel()
            with pytest.raises(VoiceProcessError) as error:
                request.result(timeout=3)
            assert error.value.code=='cancelled'
        monkeypatch.delenv('SCOTT_TEST_PREPARE_MODE')
        voice.prepare()
        wait_for(lambda:not voice.status()['running'])
        assert not voice.status()['model_loaded']


def test_old_worker_reports_unsupported_preparation(config):
    config.worker.write_text(FAKE_WORKER.replace("features=['prepare_v1']",'features=[]'),encoding='utf-8')
    with ScottVoiceProcess(config) as voice:
        with pytest.raises(VoiceProcessError) as error:
            voice.prepare()
        assert error.value.code=='prepare_unavailable'
        assert voice.synthesize('Прежняя озвучка.').path


def test_complete_cache_reused_without_starting_another_process(config,monkeypatch):
    monkeypatch.setenv('SCOTT_TEST_API_KEY','synthetic-test-secret')
    with ScottVoiceProcess(config) as voice:
        first = voice.synthesize('Готово.')
        pid = voice.status()['pid']
        assert not first.cached and pid
        hit = voice.synthesize('Готово.')
        assert hit.cached and hit.path==first.path and voice.status()['pid']==pid
        other = voice.synthesize('Слушаю.')
        assert other.path!=first.path and voice.status()['pid']==pid
        assert not (config.cache_dir/'secret-leaked').exists()
        voice.cancel()
        assert not voice.status()['running']
        assert voice.synthesize('Готово.').cached
        assert not voice.status()['running']
    with ScottVoiceProcess(config) as reloaded:
        assert reloaded.synthesize('Готово.').cached
        assert not reloaded.status()['running']
    metadata = json.loads(Path(first.path).with_suffix('.json').read_text())
    assert 'text' not in metadata and not list(config.cache_dir.glob('.pending-*'))


def test_worker_exits_when_owner_is_killed(config):
    script = '''
import json,os,sys,threading,time
from scott_voice_process import ScottVoiceProcess,VoiceProcessConfig
c=VoiceProcessConfig.from_wire(json.loads(sys.argv[1]))
voice=ScottVoiceProcess(c)
threading.Thread(target=lambda:voice.synthesize('отмена'),daemon=True).start()
deadline=time.monotonic()+5
while not list(c.cache_dir.glob('.pending-*.wav')):
    if time.monotonic()>deadline:sys.exit(2)
    time.sleep(.01)
os._exit(0)
'''
    owner = subprocess.Popen([sys.executable, '-c', script, json.dumps(config.wire())])
    child = None
    try:
        wait_for(lambda: (config.cache_dir/'worker-pid').is_file())
        pid = int((config.cache_dir/'worker-pid').read_text())
        try:
            child = psutil.Process(pid)
        except psutil.NoSuchProcess:
            pass
        assert owner.wait(timeout=6) == 0
        wait_for(lambda: not psutil.pid_exists(pid))
    finally:
        if owner.poll() is None:
            owner.kill()
            owner.wait(timeout=3)
        if child and child.is_running():
            child.kill()
            child.wait(timeout=3)


def test_simultaneous_requests_wait_for_one_complete_result(config):
    with ScottVoiceProcess(config) as voice,ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(voice.synthesize,['Готово.','Готово.']))
        assert results[0].path==results[1].path
        assert sum(result.cached for result in results)==1
        assert not list(config.cache_dir.glob('.pending-*'))


def test_timeout_kills_worker_cleans_partial_audio_and_can_restart(config):
    with ScottVoiceProcess(config,timeout=.2,startup_timeout=3) as voice:
        with pytest.raises(VoiceProcessError) as failed:
            voice.synthesize('таймаут')
        assert failed.value.code=='timeout'
        wait_for(lambda: not psutil.pid_exists(int((config.cache_dir/'worker-pid').read_text())))
        assert not voice.status()['running'] and not list(config.cache_dir.glob('.pending-*'))
        assert not list(config.cache_dir.glob('scott-voice-*.wav'))
        assert not voice.synthesize('Готово.').cached


def test_worker_crash_does_not_publish_partial_cache(config):
    with ScottVoiceProcess(config) as voice:
        with pytest.raises(VoiceProcessError):
            voice.synthesize('сбой')
        assert not voice.status()['running'] and not list(config.cache_dir.glob('.pending-*'))
        assert not voice.synthesize('Готово.').cached


def test_cancellation_interrupts_a_pending_synthesis(config):
    with ScottVoiceProcess(config) as voice,ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(voice.synthesize,'отмена')
        wait_for(lambda: config.cache_dir.exists() and list(config.cache_dir.glob('.pending-*.wav')))
        voice.cancel()
        with pytest.raises(VoiceProcessError) as failed:
            pending.result(timeout=3)
        assert failed.value.code=='cancelled'
        wait_for(lambda: not psutil.pid_exists(int((config.cache_dir/'worker-pid').read_text())))
        assert not voice.status()['running'] and not list(config.cache_dir.glob('.pending-*'))
        assert not voice.synthesize('Готово.').cached


def test_timeout_also_stops_owned_descendants(config):
    with ScottVoiceProcess(config,timeout=.7,startup_timeout=3) as voice:
        with pytest.raises(VoiceProcessError) as failed:
            voice.synthesize('дочерний')
        assert failed.value.code=='timeout'
        child_pid = int((config.cache_dir/'child-pid').read_text())
        worker_pid = int((config.cache_dir/'worker-pid').read_text())
        wait_for(lambda: not psutil.pid_exists(child_pid) and not psutil.pid_exists(worker_pid))
        assert not list(config.cache_dir.glob('.pending-*'))


def test_corrupted_cache_is_regenerated(config):
    with ScottVoiceProcess(config) as voice:
        first = voice.synthesize('Готово.')
        Path(first.path).write_bytes(b'broken WAV')
        regenerated = voice.synthesize('Готово.')
        assert not regenerated.cached and regenerated.path==first.path
        with wave.open(regenerated.path) as audio:
            assert audio.getnframes()==2400


def test_profile_and_recipe_changes_invalidate_cache(config):
    with ScottVoiceProcess(config) as voice:
        original = voice.synthesize('Готово.','natural')
        coloured = voice.synthesize('Готово.','scott')
        assert original.path!=coloured.path
    config.profiles_json.write_text('[{"updated":true}]')
    with ScottVoiceProcess(config) as updated:
        new = updated.synthesize('Готово.','natural')
        assert not new.cached and new.path!=original.path


def test_idle_worker_releases_resources_and_leaves_disk_cache(config):
    with ScottVoiceProcess(config,idle_timeout=.1) as voice:
        first = voice.synthesize('Готово.')
        wait_for(lambda: not voice.status()['running'])
        hit = voice.synthesize('Готово.')
        assert hit.cached and hit.path==first.path and not voice.status()['running']


def test_reference_checksum_failure_and_invalid_request_never_start_worker(config):
    with ScottVoiceProcess(config) as voice:
        for text,profile in [('', 'scott'),('x'*1201,'scott'),('Готово.','unknown')]:
            with pytest.raises(ValueError):
                voice.synthesize(text,profile)
        assert not voice.status()['running']
    (config.reference_json.parent/'scott-reference.wav').write_bytes(b'changed reference')
    with pytest.raises(ValueError,match='reference hash'):
        ScottVoiceProcess(config)


def test_close_disallows_more_requests(config):
    voice = ScottVoiceProcess(config)
    voice.close()
    with pytest.raises(VoiceProcessError) as failed:
        voice.synthesize('Готово.')
    assert failed.value.code=='closed' and not voice.status()['running']
