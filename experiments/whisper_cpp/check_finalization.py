"""Force short pool limits and verify synthetic EOT, bounded seek and reload."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from benchmark import ROOT, Native, read_prompt_tokens, write_json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('worker','plain-worker','model','corpus','output','tokens'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    for name in ('worker','plain_worker','model','corpus','output','tokens'):
        setattr(a,name,getattr(a,name).resolve())
    assert a.output.is_relative_to(ROOT/'reports') and not a.output.exists()
    a.output.mkdir(parents=True);checks=[];ids=read_prompt_tokens(a.tokens)
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)))
        write_json(a.output/'partial.json',checks)
        assert value,name
    for limit in (1,2,3,220):
        folder=a.output/str(limit);folder.mkdir()
        opts=SimpleNamespace(worker=a.worker,model=a.model,device='cpu',threads=8,fallback=0,
            owner_watch=True,decoder_trace=True,finished_pool=True,pool_sample_limit=limit,prompt_token_ids=ids)
        worker=Native(opts,a.corpus,folder)
        try:
            check(f'{limit}_ready',worker.ready['finished_pool']['sample_limit']==limit)
            result=worker.transcribe(dict(id=0,pcm='000.f32'),timeout_ms=15000)
            write_json(folder/'decode.json',result)
            check(f'{limit}_result',not result.get('error'))
            trace=result['decoder_trace'];events=trace['events']
            ranks=[e for e in events if e['kind']=='pool_rank']
            check(f'{limit}_trace',trace['complete'] and bool(ranks))
            candidates=[c for e in ranks for c in e['candidates']]
            check(f'{limit}_bounded',all(0<len(c['ids'])<=limit for c in candidates) and
                all(len(e['candidates'])<=5 for e in ranks))
            check(f'{limit}_eot',all(c['sampled_eot']==(limit==220) and
                (limit==220 or c['eot_logprob']==0) for c in candidates))
            check(f'{limit}_seek',all(c['seek_delta']>0 for c in candidates))
            check(f'{limit}_unique',all(len({tuple(c['ids']) for c in e['candidates']})==len(e['candidates']) for e in ranks))
            check(f'{limit}_score',all(abs(c['score']-c['sum_logprobs_all']/max(1,c['result_len']))<1e-6 and
                abs(c['avg_logprobs']-c['sum_logprobs_all']/(c['result_len']+1))<1e-6 for c in candidates))
            sums=True;synthetic=True
            for rank in ranks:
                post=next(e for e in events if e['kind']=='post_rank' and e['seek']==rank['seek'])
                winner=post['decoders'][post['selected']];selected=rank['candidates'][rank['selected']]
                sums &= abs(sum(winner['token_logprobs'])+selected['eot_logprob']-selected['sum_logprobs_all'])<1e-5
                if limit<220:
                    step=[e for e in events if e['kind']=='step' and e['seek']==rank['seek']][-1]
                    synthetic &= all(any(abs(c['sum_logprobs_all']-d['sum_logprobs_all'])<1e-6 for d in step['decoders']) for c in rank['candidates'])
            check(f'{limit}_token_sum',sums)
            check(f'{limit}_synthetic_sum',synthetic)
            again=worker.transcribe(dict(id=1,pcm='000.f32'),timeout_ms=15000)
            check(f'{limit}_repeat',not again.get('error') and again['text']==result['text'])
        finally:worker.close()
        check(f'{limit}_eof',worker.process.returncode==0)
    invalid=[('zero',dict(pool_sample_limit=0,finished_pool=True)),
        ('large',dict(pool_sample_limit=221,finished_pool=True)),
        ('bool',dict(pool_sample_limit=True,finished_pool=True)),
        ('float',dict(pool_sample_limit=2.5,finished_pool=True)),
        ('string',dict(pool_sample_limit='2',finished_pool=True)),
        ('null',dict(pool_sample_limit=None,finished_pool=True)),
        ('array',dict(pool_sample_limit=[2],finished_pool=True)),
        ('overflow',dict(pool_sample_limit=18446744073709551615,finished_pool=True)),
        ('without_pool',dict(pool_sample_limit=2)),('plain',dict(pool_sample_limit=220,finished_pool=True))]
    for name,opts in invalid:
        worker=a.plain_worker if name=='plain' else a.worker
        with (a.output/(name+'.log')).open('w',encoding='utf-8') as log:
            result=subprocess.run([str(worker),str(a.model),str(a.corpus),'cpu','8',str(a.corpus/'prompt.txt'),'0',json.dumps(opts)],
                input='',text=True,encoding='utf-8',stdout=subprocess.PIPE,stderr=log,timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        check('reject_'+name,result.returncode==2 and '"event":"ready"' not in result.stdout)
    write_json(a.output/'result.json',dict(checks=checks,commands_executed=False,microphone_used=False,quality_measured=False))
    print(json.dumps(dict(passed=len(checks))))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    main()
