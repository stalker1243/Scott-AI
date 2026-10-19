"""Real decoding: separate bounded finished candidates, five active paths and ranking."""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from benchmark import ROOT, Native, read_prompt_tokens, write_json


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('worker', 'plain-worker', 'model', 'corpus', 'output', 'tokens'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    for name in ('worker', 'plain_worker', 'model', 'corpus', 'output', 'tokens'):
        setattr(a, name, getattr(a, name).resolve())
    assert a.output.is_relative_to(ROOT/'reports') and not a.output.exists()
    a.output.mkdir(parents=True)
    ids = read_prompt_tokens(a.tokens)
    checks = []
    def check(name, value):
        checks.append(dict(name=name, passed=bool(value)))
        write_json(a.output/'partial.json', checks)
        assert value, name
    continued = False
    for beam in (1, 5, 8):
        out = a.output/str(beam); out.mkdir()
        options = SimpleNamespace(worker=a.worker, model=a.model, device='cpu', threads=8,
            fallback=0, prompt_token_ids=ids, decoder_trace=True, owner_watch=True,
            finished_pool=True, beam_size=beam)
        worker = Native(options, a.corpus, out)
        try:
            check(f'{beam}_ready', worker.ready['finished_pool']['enabled'] and
                worker.ready['finished_pool']['capacity'] == beam and
                worker.ready['finished_pool']['topk'] == beam+1)
            result = worker.transcribe(dict(id=0, pcm='000.f32'))
            write_json(out/'decode.json', result)
            trace = result['decoder_trace']; events = trace['events']
            select = [e for e in events if e['kind'] == 'pool_select']
            ranks = [e for e in events if e['kind'] == 'pool_rank']
            check(f'{beam}_trace', trace['complete'] and bool(select) and bool(ranks))
            check(f'{beam}_prefix', next(e for e in events if e['kind']=='prompt')['prompt'][1:-3] == ids)
            check(f'{beam}_bounded', all(0 <= e['finished_count'] <= beam and
                0 <= e['active_count'] <= beam and e['topk'] == beam+1 for e in select))
            check(f'{beam}_active', all(e['active_count'] == beam for e in select if e['finished_count'] < beam))
            continued |= any(0 < e['finished_count'] < beam and e['active_count'] == beam for e in select)
            check(f'{beam}_unique', all(len({tuple(c['ids']) for c in e['candidates']}) ==
                len(e['candidates']) <= beam for e in ranks))
            check(f'{beam}_score', all(math.isclose(c['score'], c['sum_logprobs_all']/max(1,c['result_len']),abs_tol=1e-6)
                and math.isclose(c['avg_logprobs'],c['sum_logprobs_all']/(c['result_len']+1),abs_tol=1e-6)
                for e in ranks for c in e['candidates']))
            check(f'{beam}_winner', all(e['selected'] >= 0 and not e['candidates'][e['selected']]['failed'] and
                e['candidates'][e['selected']]['score'] == max(c['score'] for c in e['candidates'] if not c['failed']) for e in ranks))
            if beam == 5:
                repeat = worker.transcribe(dict(id=1, pcm='000.f32'))
                check('repeat', repeat['text'] == result['text'] and repeat['decoder_trace']['complete'])
        finally:
            worker.close()
        check(f'{beam}_eof', worker.process.returncode == 0)
    check('continues_after_eot', continued)
    for value, expected in ((True, 2), (False, 0)):
        with (a.output/f'plain-{value}.log').open('w', encoding='utf-8') as log:
            result = subprocess.run([str(a.plain_worker),str(a.model),str(a.corpus),'cpu','8',
                str(a.corpus/'prompt.txt'),'0',json.dumps(dict(finished_pool=value))],input='',text=True,
                encoding='utf-8',stdout=subprocess.PIPE,stderr=log,timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        check(f'plain_{value}',result.returncode==expected and ('"event":"ready"' in result.stdout)==(not value))
    write_json(a.output/'result.json',dict(checks=checks,commands_executed=False,microphone_used=False))
    print(json.dumps(dict(passed=len(checks))))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    main()
