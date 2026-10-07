"""Exercise real model preparation through ASGI HTTP; no main app, mic or speech."""
import asyncio
import argparse
from dataclasses import replace
from pathlib import Path
import json
import sys
import time
import psutil
import httpx
from fastapi import FastAPI

from check_streaming import protected
from trial_utils import ROOT, save_json
import scott_voice_engine as engines
from scott_voice_process import ScottVoiceProcess
from voice_prepare import VoicePreparation
import voice_prepare_endpoints as endpoints


async def main(folder):
    folder.mkdir(parents=True,exist_ok=True)
    if (folder/'api.json').exists():
        raise ValueError('Keep existing measurements; choose a fresh folder in the script')
    before=protected()
    config=replace(engines.default_config(),cache_dir=folder/'cache')
    model=engines.ScottVoiceEngine(config)
    jobs=VoicePreparation(lambda:model)
    endpoints.preparation=jobs
    assert model.describe()['available']
    app=FastAPI();app.include_router(endpoints.router)
    @app.get('/health')
    async def health(): return dict(status='online')
    samples,errors=[],[]
    report=dict(method='ASGI_prepare_router_real_worker',microphone_opened=False,
        audio_output_opened=False,new_synthesis=False,protected_sha256=before)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as api:
        async def request(path,body=None):
            start=time.perf_counter()
            response=await (api.get(path) if body is None else api.post(path,json=body))
            if response.status_code!=200: errors.append(dict(path=path,status=response.status_code))
            samples.append(time.perf_counter()-start)
            assert response.status_code==200
            return response.json()
        try:
            state=await request('/voice/prepare',{})
            while not (model._client and 'prepare_v1' in model._client._features):
                await request('/health');await asyncio.sleep(.02)
            await asyncio.sleep(.5)
            start=time.perf_counter()
            await request('/voice/prepare/cancel',{'id':state['id']})
            while jobs.snapshot()['state']=='cancelling':
                await request('/health');await asyncio.sleep(.02)
            report['cancel_loading_seconds']=time.perf_counter()-start
            assert not model.model_status()['model_loaded']
            state=await request('/voice/prepare',{})
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                await request('/health')
                current=await request('/voice/prepare')
                if current['state'] not in ('running','cancelling'): break
                await asyncio.sleep(.05)
            assert current['state']=='complete' and current['model_loaded']
            prepared_pid=model._client.status()['pid']
            model.cancel(preserve_idle=True)
            assert model._client.status()['pid']==prepared_pid
            assert jobs.snapshot()['model_loaded']
            report['new_request_preserves_idle_model']=True
            start=time.perf_counter()
            await request('/voice/prepare/cancel',{'id':state['id']})
            report['release_loaded_seconds']=time.perf_counter()-start
            assert not model.model_status()['model_loaded']
            model.factory=lambda *args,**kwargs:ScottVoiceProcess(*args,**kwargs,idle_timeout=.5)
            await request('/voice/prepare',{})
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                current=await request('/voice/prepare')
                if current['state'] not in ('running','cancelling'): break
                await request('/health');await asyncio.sleep(.05)
            assert current['state']=='complete' and current['model_loaded']
            owner=psutil.Process(model._client.status()['pid'])
            owned=[owner,*owner.children(recursive=True)]
            start=time.perf_counter()
            deadline=time.monotonic()+5
            while time.monotonic()<deadline and any(p.is_running() for p in owned):
                await request('/health');await asyncio.sleep(.02)
            assert not any(p.is_running() for p in owned)
            assert not (await request('/voice/prepare'))['model_loaded']
            report['test_idle_timeout_seconds']=.5
            report['idle_release_seconds']=time.perf_counter()-start
            assert not list(config.cache_dir.glob('*.wav'))
            assert not list(config.cache_dir.glob('*.json'))
        finally:
            jobs.close();model.close()
    report.update(http_requests=len(samples),http_errors=errors,http_max_seconds=max(samples),
        protected_files_unchanged=before==protected(),worker_running=model.model_status().get('running',False))
    assert report['protected_files_unchanged'] and not report['worker_running']
    save_json(folder/'api.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='protected_sha256'}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'reports/voice-preparation/api')
    asyncio.run(main(parser.parse_args().output))
