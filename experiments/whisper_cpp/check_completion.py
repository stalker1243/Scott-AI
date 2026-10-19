"""Real worker: completion flags, sampled EOT scores, bounded trace and plain refusal."""
import argparse
import json
import math
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
from benchmark import ROOT, Native, read_prompt_tokens, write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('worker','model','corpus','output','tokens','plain-worker'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    for name in ('worker','model','corpus','output','tokens','plain_worker'):
        setattr(args,name,getattr(args,name).resolve())
    assert args.output.is_relative_to(ROOT/'reports') and not args.output.exists()
    args.output.mkdir(parents=True)
    ids=read_prompt_tokens(args.tokens)
    checks=[]
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)))
        write_json(args.output/'partial.json',checks)
        assert value,name
    for name,finish,rank in [('off',False,False),('rank',False,True),('finish',True,False),('both',True,True)]:
        folder=args.output/name; folder.mkdir()
        options=SimpleNamespace(worker=args.worker,model=args.model,device='cpu',threads=8,fallback=0,
            prompt_token_ids=ids,decoder_trace=True,owner_watch=True,finish_at_eot=finish,rank_eot=rank)
        worker=Native(options,args.corpus,folder)
        try:
            check(name+'_ready',worker.ready['candidate_completion']==dict(finish_at_eot=finish,rank_eot=rank))
            result=worker.transcribe(dict(id=0,pcm='000.f32'))
            trace=result['decoder_trace']; events=trace['events']
            check(name+'_complete',trace['complete'])
            check(name+'_prefix',next(e for e in events if e['kind']=='prompt')['prompt'][1:-3]==ids)
            terminals=[e for e in events if e['kind']=='termination']
            check(name+'_terminations',bool(terminals))
            if finish: check(name+'_eot_only',all(e['reason']=='eot' for e in terminals))
            before=next(e for e in events if e['kind']=='pre_rank')['decoders']
            after=next(e for e in events if e['kind']=='post_rank')['decoders']
            verified=0; with_eot=0
            for pre,post in zip(before,after):
                if post['failed'] or post['result_len']<=0: continue
                count=post['result_len']; base=sum(pre['token_logprobs'][:count])/count
                trailing_eot=pre['ids'][-1:]==[50257] and len(pre['ids'])==count+1
                if trailing_eot: with_eot+=1
                expected=base+(pre['token_logprobs'][-1]/count if rank and trailing_eot else 0)
                assert math.isfinite(post['score']) and abs(post['score']-expected)<1e-6
                assert abs(post['avg_logprobs']-base)<1e-6
                verified+=1
            check(name+'_score_contract',verified>0)
            if finish: check(name+'_sampled_eot',with_eot>0)
            again=worker.transcribe(dict(id=1,pcm='000.f32'))
            check(name+'_repeat',result['text']==again['text'] and again['decoder_trace']['complete'])
        finally: worker.close()
        check(name+'_exit',worker.process.returncode==0)
    for name in ('finish_at_eot','rank_eot'):
        with (args.output/(name+'-plain.log')).open('w',encoding='utf-8') as log:
            result=subprocess.run([str(args.plain_worker),str(args.model),str(args.corpus),'cpu','8',
                str(args.corpus/'prompt.txt'),'0',json.dumps({name:True})],input='',text=True,
                encoding='utf-8',stdout=subprocess.PIPE,stderr=log,timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        check('plain_rejects_'+name,result.returncode==2 and '"event":"ready"' not in result.stdout)
    write_json(args.output/'result.json',dict(checks=checks,model_quality_measured=False))
    print(json.dumps(dict(passed=len(checks))))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    main()
