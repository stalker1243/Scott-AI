"""Real beam: distinct first tokens, preserved prompt, clean repeat and plain refusal."""
import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
from benchmark import ROOT, Native, read_prompt_tokens, write_json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('worker','plain-worker','model','corpus','output','tokens'):
        p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    for name in ('worker','plain_worker','model','corpus','output','tokens'):
        setattr(args,name,getattr(args,name).resolve())
    assert args.output.is_relative_to(ROOT/'reports') and not args.output.exists()
    args.output.mkdir(parents=True)
    ids=read_prompt_tokens(args.tokens); checks=[]
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)))
        write_json(args.output/'partial.json',checks)
        assert value,name
    for mode,enabled in [('off',False),('distinct',True)]:
        out=args.output/mode; out.mkdir()
        options=SimpleNamespace(worker=args.worker,model=args.model,device='cpu',threads=8,fallback=0,
            prompt_token_ids=ids,decoder_trace=True,owner_watch=True,deduplicate_first_step=enabled,deterministic_topk=True)
        worker=Native(options,args.corpus,out)
        try:
            check(mode+'_ready',worker.ready['deduplicate_first_step']==enabled)
            first=worker.transcribe(dict(id=0,pcm='000.f32'))
            trace=first['decoder_trace']; e=next(e for e in trace['events'] if e['kind']=='step')
            check(mode+'_five_slots',len(e['decoders'])==5)
            unique=len({d['ids'][-1] for d in e['decoders']})
            check(mode+'_unique_tokens',unique==(5 if enabled else 1))
            check(mode+'_prefix',next(e for e in trace['events'] if e['kind']=='prompt')['prompt'][1:-3]==ids)
            check(mode+'_complete',trace['complete'])
            second=worker.transcribe(dict(id=1,pcm='000.f32'))
            check(mode+'_repeat',first['text']==second['text'] and second['decoder_trace']['complete'])
        finally: worker.close()
        check(mode+'_eof',worker.process.returncode==0)
    for key in ('deduplicate_first_step','deterministic_topk'):
        with (args.output/(key+'-plain.log')).open('w',encoding='utf-8') as log:
            invalid=subprocess.run([str(args.plain_worker),str(args.model),str(args.corpus),'cpu','8',
                str(args.corpus/'prompt.txt'),'0',json.dumps({key:True})],input='',text=True,
                encoding='utf-8',stdout=subprocess.PIPE,stderr=log,timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        check('plain_refuses_'+key,invalid.returncode==2 and '"event":"ready"' not in invalid.stdout)
    write_json(args.output/'result.json',dict(checks=checks,model_quality_measured=False))
    print(json.dumps(dict(passed=len(checks))))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    main()
