"""Check the isolated voice process and persistent cache; never play or execute speech."""
from pathlib import Path
import argparse
import json
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0,str(ROOT))

from backend.scott_voice_process import ScottVoiceProcess,VoiceProcessConfig
from benchmark_base import Backend
from trial_utils import save_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',choices=['natural','restrained','scott','digital'],default='scott')
    parser.add_argument('--rms-norm',action='store_true',help='Use the experimental faster synthesis candidate')
    parser.add_argument('--recognize',action='store_true')
    args = parser.parse_args()
    config = VoiceProcessConfig(python=Path(sys.executable),worker=HERE/'voice_worker.py',
        model_dir=HERE/'models/base',reference_json=ROOT/'reports/voice-design/reference/reference.json',
        profiles_json=HERE/'robotic_profiles.json',cache_dir=ROOT/'audio_cache/scott-voice',rms_norm=args.rms_norm)
    phrases = ['Готово.','Слушаю.','Соединение восстановлено.']
    result = dict(profile=args.profile,rms_norm=args.rms_norm,results=[],health_errors=[])
    backend = Backend('http://127.0.0.1:8000')
    health, _ = backend.get('/health')
    result['backend_before'] = health['status']
    finished = threading.Event()
    timings = []
    def monitor():
        while not finished.is_set():
            try:
                _,seconds = backend.get('/health',timeout=2)
                timings.append(seconds)
            except Exception as error:
                result['health_errors'].append(type(error).__name__)
            finished.wait(.2)
    checker = threading.Thread(target=monitor,daemon=True)
    checker.start()
    try:
        with ScottVoiceProcess(config) as voice:
            result['import_did_not_load_torch'] = 'torch' not in sys.modules
            for phrase in phrases:
                started = time.perf_counter()
                audio = voice.synthesize(phrase,args.profile)
                seconds = time.perf_counter()-started
                row = dict(text=phrase,seconds=audio.seconds,first_seconds=round(seconds,4),
                           cached=audio.cached,audio=str(Path(audio.path).relative_to(ROOT)).replace('\\','/'),
                           worker_pid=voice.status()['pid'])
                started = time.perf_counter()
                hit = voice.synthesize(phrase,args.profile)
                row['cache_hit_seconds'] = round(time.perf_counter()-started,6)
                assert hit.cached and hit.path==audio.path
                if args.recognize:
                    row['recognition'] = backend.transcribe(Path(audio.path),phrase)
                result['results'].append(row)
                print(json.dumps(row,ensure_ascii=True),flush=True)
            voice.cancel()
            result['worker_stopped'] = not voice.status()['running']
            started = time.perf_counter()
            hit = voice.synthesize(phrases[0],args.profile)
            result['disk_cache_without_worker_seconds'] = round(time.perf_counter()-started,6)
            result['disk_cache_without_worker'] = hit.cached and not voice.status()['running']
        result['parent_did_not_load_torch'] = 'torch' not in sys.modules
    finally:
        finished.set()
        checker.join(timeout=3)
    result['health_requests'] = len(timings)
    result['health_max_seconds'] = round(max(timings),4) if timings else None
    report = ROOT/'reports/voice-service'
    report.mkdir(parents=True,exist_ok=True)
    save_json(report/'service.json',result)
    print(json.dumps({key:value for key,value in result.items() if key!='results'},ensure_ascii=True),flush=True)


if __name__=='__main__':
    main()
