"""Compare original/RMSNorm streams in ABBA order without playback or commands."""
from dataclasses import replace
from pathlib import Path
import argparse
import json
import shutil
import sys
import time

from check_streaming import protected,join_audio
from trial_utils import ROOT,cases,save_json
from build_stream_preview import schedule,metrics
from benchmark_base import Backend
from scott_voice_engine import default_config,inspect_installation
from scott_voice_process import ScottVoiceProcess,VoiceProcessError,checksum


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'reports/voice-stream-speed')
    parser.add_argument('--recognize',action='store_true',help='Recognize existing WAVs after all timed runs.')
    parser.add_argument('--order',choices=('abba','ba'),default='abba')
    args=parser.parse_args();folder=args.output
    if (folder/'speed.json').exists(): raise ValueError('Choose a new output folder')
    folder.mkdir(parents=True,exist_ok=True)
    before=protected();base=default_config()
    assert not inspect_installation(base)
    report=dict(order=['original','accelerated','accelerated','original'] if args.order=='abba' else ['accelerated','original'],results=[],protected_sha256=before,
        device=base.device,cpu_threads=base.cpu_threads,note='Separate workers/caches; no STT during timing. First case is cold.')
    dataset=[c for c in cases() if c['id'] in ('status','technical','numbers')]
    try:
        for index,mode in enumerate(report['order']):
            name=f'{index+1}-{mode}';run=folder/name;run.mkdir()
            config=replace(base,cache_dir=run/'cache',rms_norm=mode=='accelerated')
            with ScottVoiceProcess(config,timeout=180,idle_timeout=0) as client:
                for case_index,case in enumerate(dataset):
                    blocks=[];records=[];begin=time.perf_counter()
                    def output(audio,last):
                        target=run/f'{case["id"]}-block-{len(blocks):02}.wav'
                        shutil.copyfile(audio.path,target);blocks.append(target)
                        records.append(dict(arrival_seconds=round(time.perf_counter()-begin,3),
                            seconds=audio.seconds,last=last,cached=audio.cached))
                    result=client.stream(case['text'],'natural',output)
                    elapsed=time.perf_counter()-begin
                    complete=run/f'{case["id"]}-complete.wav';shutil.copyfile(result.path,complete)
                    joined=run/f'{case["id"]}-joined.wav';join_audio(blocks,joined)
                    timed=run/f'{case["id"]}-timed.wav';join_audio(blocks,timed,[r['arrival_seconds'] for r in records])
                    row=dict(**case,mode=mode,run=index+1,cold=case_index==0,blocks=records,
                        first_audio_seconds=records[0]['arrival_seconds'],total_seconds=round(elapsed,3),audio_seconds=result.seconds,
                        complete=str(complete.relative_to(folder)).replace('\\','/'),
                        joined=str(joined.relative_to(folder)).replace('\\','/'),timed=str(timed.relative_to(folder)).replace('\\','/'),
                        complete_sha256=checksum(complete),real_time_factor=round(elapsed/result.seconds,3))
                    row['schedule']=schedule(row);row['signal']=metrics(joined)
                    assert abs(row['signal']['seconds']-result.seconds)<.002
                    if mode=='original':
                        row['accepted_wav_equal']=row['complete_sha256']==checksum(ROOT/f'reports/voice-base/base-{case["id"]}.wav')
                        assert row['accepted_wav_equal']
                    report['results'].append(row);save_json(folder/'speed.json',report)
                    print(json.dumps(dict(run=index+1,mode=mode,case=case['id'],first=row['first_audio_seconds'],total=row['total_seconds'],
                        speech=row['audio_seconds'],gaps=round(row['schedule']['gap_seconds'],3),rtf=row['real_time_factor'])),flush=True)
                if index==2:
                    original_files=set(config.cache_dir.glob('scott-voice-*.wav'));cancelled=[]
                    def cancel(*args):
                        begin=time.perf_counter();client.cancel();cancelled.append(time.perf_counter()-begin)
                    try:
                        client.stream('Проверка отмены ускоренного синтеза.','natural',cancel)
                        raise AssertionError('Cancelled stream succeeded')
                    except VoiceProcessError as error: assert error.code=='cancelled'
                    report['cancel']=dict(seconds=round(cancelled[0],3),worker_running=client.status()['running'])
                    assert not report['cancel']['worker_running'] and not list(config.cache_dir.glob('.stream-*'))
                    assert original_files==set(config.cache_dir.glob('scott-voice-*.wav'))
        assert 'torch' not in sys.modules
        if args.recognize:
            backend=Backend('http://127.0.0.1:8000');backend.get('/health')
            for row in report['results']:
                row['recognition']={kind:backend.transcribe(folder/row[kind],row['text']) for kind in ('complete','joined')}
                save_json(folder/'speed.json',report)
                print(json.dumps(dict(run=row['run'],case=row['id'],wer={k:v['word_error_rate'] for k,v in row['recognition'].items()})),flush=True)
            assert all(v['success'] and v['word_error_rate']==0 for row in report['results'] for v in row['recognition'].values())
    finally:
        report['protected_files_unchanged']=before==protected();save_json(folder/'speed.json',report)
    assert report['protected_files_unchanged']


if __name__=='__main__': main()
