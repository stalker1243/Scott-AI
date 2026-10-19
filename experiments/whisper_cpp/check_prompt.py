"""Real diagnostic worker: exact prompt, boundary, restart, plain refusal."""
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
    for name in ('worker','model','corpus','output','tokens'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--plain-worker',type=Path)
    args=p.parse_args()
    for name in ('worker','model','corpus','output','tokens','plain_worker'):
        value=getattr(args,name)
        if value is not None: setattr(args,name,value.resolve())
    if args.output.exists() or not args.output.is_relative_to(ROOT/'reports'):
        p.error('Choose a new experimental output')
    ids=read_prompt_tokens(args.tokens)
    args.output.mkdir(parents=True)
    checks=[]
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)))
        write_json(args.output/'partial.json',checks)
        assert value,name
    for name,tokens in [('exact',ids),('max',[1]*220)]:
        folder=args.output/name; folder.mkdir()
        options=SimpleNamespace(worker=args.worker,model=args.model,device='cpu',threads=8,fallback=0,
            prompt_token_ids=tokens,decoder_trace=True,owner_watch=True)
        worker=Native(options,args.corpus,folder)
        try:
            check(name+'_ready_ids',worker.ready['prompt_tokens']['ids']==tokens)
            first=worker.transcribe(dict(id=0,pcm='000.f32'))
            check(name+'_decode',not first.get('error'))
            trace=first['decoder_trace']
            prompt=next(e for e in trace['events'] if e['kind']=='prompt')['prompt']
            check(name+'_trace_content',prompt[1:-3]==tokens)
            check(name+'_trace_length',len(prompt)==len(tokens)+4)
            second=worker.transcribe(dict(id=1,pcm='000.f32'))
            check(name+'_repeat_text',first['text']==second['text'])
            prompts=[e['prompt'] for e in second['decoder_trace']['events'] if e['kind']=='prompt']
            check(name+'_repeat_prompt',prompts and prompts[0]==prompt)
            check(name+'_complete',trace['complete'] and second['decoder_trace']['complete'])
        finally: worker.close()
        check(name+'_clean_exit',worker.process.returncode==0)
    if args.plain_worker:
        with (args.output/'plain.log').open('w',encoding='utf-8') as log:
            result=subprocess.run([str(args.plain_worker),str(args.model),str(args.corpus),'cpu','8',
                str(args.corpus/'prompt.txt'),'0',json.dumps(dict(prompt_token_ids=ids))],
                input='',text=True,encoding='utf-8',stdout=subprocess.PIPE,stderr=log,
                timeout=10,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        check('plain_refuses_exact_tokens',result.returncode==2 and '"event":"ready"' not in result.stdout)
    write_json(args.output/'result.json',dict(checks=checks,model_quality_measured=False))
    print(json.dumps(dict(passed=len(checks))))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    main()
