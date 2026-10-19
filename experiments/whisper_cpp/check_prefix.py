"""Real offline probe: bounded inputs, output isolation and positive CPU replay."""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from benchmark import ROOT, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('worker','model','corpus','output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    for name in ('worker','model','corpus','output'): setattr(args,name,getattr(args,name).resolve())
    assert args.output.is_relative_to(ROOT/'reports') and not args.output.exists()
    args.output.mkdir(parents=True)
    checks = []
    flags = subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    base = dict(protocol=1,cases=[dict(id=0, pcm='valid.f32',mel='mel.f32',n_mels=80,
        plans=[dict(name='small-fixture',prefix=[50258,50263,50359],sequence=[50364,22965,1631,403,50257])])])
    mel = struct.pack('<f',0.5)*(80*3000)  # Controlled tensor; not a recognition quality test.
    def case(name, data, mutate=None, owner=None):
        folder=args.output/name; folder.mkdir()
        shutil.copy2(args.corpus/'000.f32',folder/'valid.f32')
        (folder/'mel.f32').write_bytes(mel)
        if mutate: mutate(folder)
        (folder/'config.json').write_text(data if isinstance(data,str) else json.dumps(data),encoding='utf-8')
        command=[str(args.worker),str(args.model),str(folder/'config.json'),'cpu','8',str(owner or os.getpid())]
        result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            timeout=180,text=True,encoding='utf-8',errors='replace',creationflags=flags)
        (folder/'stderr.log').write_text(result.stderr,encoding='utf-8')
        return folder,result,command
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)))
        write_json(args.output/'partial.json',checks)
        assert value,name
    bad=[]
    def changed(name,modify):
        config=copy.deepcopy(base); modify(config); bad.append((name,config))
    changed('protocol',lambda c:c.update(protocol=2))
    changed('cases_empty',lambda c:c.update(cases=[]))
    changed('cases_large',lambda c:c.update(cases=c['cases']*33))
    changed('plans_empty',lambda c:c['cases'][0].update(plans=[]))
    changed('plans_large',lambda c:c['cases'][0].update(plans=c['cases'][0]['plans']*9))
    changed('prefix_empty',lambda c:c['cases'][0]['plans'][0].update(prefix=[]))
    changed('prefix_large',lambda c:c['cases'][0]['plans'][0].update(prefix=[1]*221))
    changed('sequence_large',lambda c:c['cases'][0]['plans'][0].update(sequence=[1]*97))
    changed('token_negative',lambda c:c['cases'][0]['plans'][0].update(sequence=[-1]))
    changed('token_large',lambda c:c['cases'][0]['plans'][0].update(sequence=[51866]))
    changed('token_bool',lambda c:c['cases'][0]['plans'][0].update(sequence=[True]))
    changed('token_fraction',lambda c:c['cases'][0]['plans'][0].update(sequence=[1.5]))
    changed('mel_bands',lambda c:c['cases'][0].update(n_mels=81))
    changed('outside',lambda c:c['cases'][0].update(pcm='../outside.f32'))
    changed('absolute',lambda c:c['cases'][0].update(pcm=str(args.corpus/'000.f32')))
    for key in ('flash_attn','full_replay'):
        changed(key+'_string',lambda c,key=key:c.update({key:'true'}))
        changed(key+'_integer',lambda c,key=key:c.update({key:1}))
    (args.output/'outside.f32').write_bytes((args.corpus/'000.f32').read_bytes())
    bad.extend([('json','{bad'),('config_large',' '* (2*1024*1024+1))])
    for name,config in bad:
        folder,result,_=case(name,config)
        check('reject_'+name,result.returncode==2 and not (folder/'cpp-output').exists()
            and 'whisper_model_load' not in result.stderr)
    for name,data in [('pcm_size',b'x'),('pcm_nan',struct.pack('<f',float('nan'))),
                      ('pcm_range',struct.pack('<f',1.1)),('pcm_empty',b''),
                      ('pcm_large',b'\0'*(16000*60*4+4)),('mel_nan',struct.pack('<f',float('nan'))+mel[4:])]:
        filename='mel.f32' if name.startswith('mel') else 'valid.f32'
        folder,result,_=case(name,base,lambda f:(f/filename).write_bytes(data))
        check('reject_'+name,result.returncode==2 and not(folder/'cpp-output').exists()
            and 'whisper_model_load' not in result.stderr)
    folder,result,_=case('wrong_owner',base,owner=os.getpid()+1000000)
    check('reject_wrong_owner',result.returncode==2 and not(folder/'cpp-output').exists())
    folder,result,command=case('positive',base)
    check('cpu_positive_exit',result.returncode==0)
    output=json.loads((folder/'cpp-output/result.json').read_text('utf-8'))
    check('cpu_two_mel_modes',len(output['rows'])==2 and {r['mode'] for r in output['rows']}=={'common','native'})
    check('cpu_special_roles',output['eot']==50257 and output['timestamp_begin']==50364)
    check('cpu_forced_tokens',all(r['prefix']==base['cases'][0]['plans'][0]['prefix'] and
        r['sequence']==base['cases'][0]['plans'][0]['sequence'] for r in output['rows']))
    for row in output['rows']:
        data=(folder/'cpp-output'/row['logits']).read_bytes()
        check('finite_logits_'+row['mode'],len(data)==5*output['vocab']*4 and
            all(abs(v[0])<1e5 for v in struct.iter_unpack('<f',data)))
    check('cpu_cache_replay',all(r['incremental_full_max_abs']<0.5 for r in output['rows']))
    original=(folder/'cpp-output/result.json').read_bytes()
    second=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,creationflags=flags)
    check('reject_output_reuse',second.returncode==2 and (folder/'cpp-output/result.json').read_bytes()==original)
    full=copy.deepcopy(base);full.update(flash_attn=False,full_replay=True)
    folder,result,_=case('full',full)
    check('cpu_full_exit',result.returncode==0)
    output=json.loads((folder/'cpp-output/result.json').read_text('utf-8'))
    check('cpu_full_options',output['flash_attn'] is False and output['full_replay'] is True)
    import array
    for row in output['rows']:
        cached=array.array('f');cached.frombytes((folder/'cpp-output'/row['logits']).read_bytes())
        uncached=array.array('f');uncached.frombytes((folder/'cpp-output'/row['full_logits']).read_bytes())
        check('cpu_full_size_'+row['mode'],len(cached)==len(uncached)==5*output['vocab'])
        delta=max(abs(x-y) for x,y in zip(cached,uncached))
        check('cpu_full_delta_'+row['mode'],abs(delta-row['incremental_full_all_steps_max_abs'])<1e-6)
        check('cpu_full_finite_'+row['mode'],all(abs(x)<1e5 for x in uncached))
    write_json(args.output/'result.json',dict(checks=checks,quality_measured=False))
    print(json.dumps(dict(passed=len(checks))))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    main()
