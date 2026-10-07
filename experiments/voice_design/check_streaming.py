"""Exercise real optional streaming offline, recording synthetic WAVs without playback."""
from dataclasses import replace
from pathlib import Path
import argparse
import json
import shutil
import sys
import threading
import time
import wave

from trial_utils import ROOT, cases, save_json
from benchmark_base import Backend
sys.path.insert(0,str(ROOT/'backend'))
from scott_voice_engine import default_config, inspect_installation
from scott_voice_process import ScottVoiceProcess,VoiceProcessError,checksum


def protected():
    names=['.env','backend/data/voice_config.json','backend/data/audio_config.json',
        'reports/voice-design/reference/scott-reference.wav','assets/scott-voice/reference/scott-reference.wav',
        'voice-runtime/reports/voice-design/reference/scott-reference.wav',
        'voice-runtime/experiments/voice_design/models/base/scott-model.json']
    return {name:checksum(ROOT/name) for name in names if (ROOT/name).is_file()}


def join_audio(paths,target,arrivals=None):
    played=0.
    with wave.open(str(target),'wb') as output:
        output.setparams((1,2,24000,0,'NONE','not compressed'))
        for index,path in enumerate(paths):
            with wave.open(str(path),'rb') as source:
                assert (source.getnchannels(),source.getsampwidth(),source.getframerate())==(1,2,24000)
                if arrivals:
                    due=arrivals[index]-arrivals[0]
                    pause=max(0.,due-played)
                    output.writeframes(b'\0\0'*round(pause*24000)); played+=pause
                output.writeframes(source.readframes(source.getnframes()))
                played+=source.getnframes()/24000


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'reports/voice-streaming')
    parser.add_argument('--recognize',action='store_true')
    parser.add_argument('--fresh-profiles',action='store_true',
        help='Generate each coloured profile without a pre-existing natural WAV.')
    args=parser.parse_args()
    if (args.output/'streaming.json').exists():
        raise ValueError('Choose a new --output directory')
    args.output.mkdir(parents=True,exist_ok=True)
    before=protected()
    config=replace(default_config(),cache_dir=args.output/'cache')
    assert not inspect_installation(config)
    backend=Backend('http://127.0.0.1:8000') if args.recognize else None
    stop=threading.Event(); health=[]; errors=[]
    def monitor():
        while not stop.is_set():
            try:
                _,elapsed=backend.get('/health',timeout=3);health.append(elapsed)
            except Exception as error: errors.append(type(error).__name__)
            stop.wait(.15)
    thread=threading.Thread(target=monitor,daemon=True) if backend else None
    if thread: thread.start()
    report=dict(device=config.device,cpu_threads=config.cpu_threads,rms_norm=config.rms_norm,
        mode='fresh_profiles' if args.fresh_profiles else 'natural_and_cached_profiles',
        protected_sha256=before,results=[])
    try:
        with ScottVoiceProcess(config,timeout=180,idle_timeout=0) as client:
            dataset=[(c,'natural') for c in cases() if c['id'] in ('status','technical','numbers')]
            status=next(c for c in cases() if c['id']=='status')
            if args.fresh_profiles:
                dataset=[(c,p) for (c,_),p in zip(dataset,('restrained','scott','digital'))]
            else:
                dataset += [(status,p) for p in ('restrained','scott','digital')]
            for case,profile in dataset:
                prefix=f'{profile}-{case["id"]}'; blocks=[]; records=[]
                start=time.perf_counter()
                def output(audio,last):
                    target=args.output/f'{prefix}-block-{len(blocks):02}.wav'
                    shutil.copyfile(audio.path,target); blocks.append(target)
                    records.append(dict(arrival_seconds=round(time.perf_counter()-start,3),audio=target.name,
                        seconds=round(audio.seconds,3),last=last,cached=audio.cached))
                result=client.stream(case['text'],profile,output)
                elapsed=time.perf_counter()-start
                complete=args.output/f'{prefix}-complete.wav'; shutil.copyfile(result.path,complete)
                joined=args.output/f'{prefix}-joined.wav'; join_audio(blocks,joined)
                timed=args.output/f'{prefix}-timed.wav';join_audio(blocks,timed,[r['arrival_seconds'] for r in records])
                with wave.open(str(joined),'rb') as decoded, wave.open(str(complete),'rb') as full:
                    assert decoded.getnframes()==full.getnframes()
                row=dict(**case,profile=profile,blocks=records,first_audio_seconds=records[0]['arrival_seconds'],
                    total_seconds=round(elapsed,3),audio_seconds=result.seconds,complete=complete.name,
                    joined=joined.name,timed=timed.name,complete_sha256=checksum(complete))
                if backend:
                    row['recognition']={kind:backend.transcribe(args.output/row[kind],case['text']) for kind in ('complete','joined')}
                report['results'].append(row);save_json(args.output/'streaming.json',report)
                print(json.dumps(dict(case=case['id'],profile=profile,first_seconds=row['first_audio_seconds'],total_seconds=row['total_seconds'],
                    wer={k:v['word_error_rate'] for k,v in row.get('recognition',{}).items()})),flush=True)
            hits=[];begin=time.perf_counter()
            hit=client.stream(status['text'],'natural',lambda audio,last:hits.append(dict(cached=audio.cached,last=last)))
            report['cache']=dict(milliseconds=round((time.perf_counter()-begin)*1000,3),callbacks=hits)
            assert hit.cached and hits==[dict(cached=True,last=True)]
        cancel_config=replace(config,cache_dir=args.output/'cancel-cache')
        with ScottVoiceProcess(cancel_config,timeout=180,idle_timeout=0) as client:
            cancelled=[]
            def cancel(audio,last):
                begin=time.perf_counter();client.cancel();cancelled.append(time.perf_counter()-begin)
            try:
                client.stream('Проверка прерывания потока завершена.','natural',cancel)
                raise AssertionError('Cancelled stream returned success')
            except VoiceProcessError as error:
                assert error.code=='cancelled'
            report['cancel']=dict(seconds=round(cancelled[0],3),worker_running=client.status()['running'],
                temporary_files=len(list(cancel_config.cache_dir.glob('.stream-*'))),complete_cache_files=len(list(cancel_config.cache_dir.glob('scott-voice-*.wav'))))
            assert not report['cancel']['worker_running'] and not report['cancel']['temporary_files'] and not report['cancel']['complete_cache_files']
        assert 'torch' not in sys.modules
    finally:
        stop.set()
        if thread: thread.join(timeout=4)
        report['health']=dict(requests=len(health),errors=errors,max_seconds=round(max(health),4) if health else None)
        report['protected_files_unchanged']=before==protected()
        save_json(args.output/'streaming.json',report)
    assert report['protected_files_unchanged']
    if backend:
        assert health and not errors
        assert all(v['success'] and v['word_error_rate']==0 for row in report['results'] for v in row['recognition'].values())
    print(json.dumps(dict(results=len(report['results']),cancel=report['cancel'],health=report['health'],protected_files_unchanged=True)))


if __name__=='__main__': main()
