"""Compare cached/full and Flash Attention on immutable complete candidates."""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
from benchmark import ROOT, isolated, sha, write_json


def load(path):
    path=path.resolve()
    assert path.is_relative_to(ROOT/'reports') and path.stat().st_size<=128*1024*1024
    return json.loads(path.read_text(encoding='utf-8'))


def member(root,name):
    relative=Path(name)
    assert not relative.is_absolute()
    path=(root/relative).resolve()
    assert path.is_relative_to(root) and path.is_file()
    return path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('output','worker','trial'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    for name in ('output','worker','trial'):setattr(a,name,getattr(a,name).resolve())
    if a.output.exists() or not a.output.is_relative_to(ROOT/'reports') or not a.worker.is_relative_to(ROOT/'reports'):
        p.error('Use a new reports output and experimental worker')
    config=load(a.trial/'config.json');previous=load(a.trial/'run.json')
    assert 1<=len(config['cases'])<=32
    a.output.mkdir(parents=True)
    inputs=[]
    for case in config['cases']:
        for key in ('pcm','mel'):
            original=member(a.trial,case[key]);destination=a.output/case[key]
            assert destination.resolve().is_relative_to(a.output)
            shutil.copy2(original,destination)
            inputs.append(dict(path=case[key],sha256=sha(original)))
    command_flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    env=dict(os.environ)
    if os.name=='nt':env['PATH']='C:/Windows/System32;C:/Windows'
    cpp_runs={}
    for label,flash in [('flash',True),('no_flash',False)]:
        folder=a.output/label;folder.mkdir()
        for item in inputs:shutil.copy2(a.output/item['path'],folder/item['path'])
        options=copy.deepcopy(config);options.update(flash_attn=flash,full_replay=True)
        write_json(folder/'config.json',options)
        with (folder/'worker.log').open('w',encoding='utf-8') as log:
            subprocess.run([str(a.worker),str(ROOT/'reports/whisper-cpp/models/turbo/ggml-model.bin'),
                str(folder/'config.json'),'gpu','8',str(os.getpid())],stdout=log,stderr=subprocess.STDOUT,
                timeout=900,check=True,env=env,creationflags=command_flags)
        result=load(folder/'cpp-output/result.json')
        assert result['flash_attn']==flash and result['full_replay']
        cpp_runs[label]=result
        print(json.dumps(dict(cpp_completed=label)),flush=True)
    checkpoint=a.output/'model-input/large-v3-turbo.pt';checkpoint.parent.mkdir()
    shutil.copy2(ROOT/'backend/data/models/whisper/large-v3-turbo.pt',checkpoint)
    try:
        isolated(ROOT/'reports/whisper-cpp/corpus/source/backend')
        import numpy as np
        import torch
        import whisper
        from whisper.decoding import DecodingTask,DecodingOptions
        torch.set_num_threads(8)
        write_json(a.output/'run.json',dict(worker_sha256=sha(a.worker),checkpoint_sha256=sha(checkpoint),
            ggml_sha256=sha(ROOT/'reports/whisper-cpp/models/turbo/ggml-model.bin'),
            previous_config_sha256=sha(a.trial/'config.json'),previous_python_sha256=sha(a.trial/'python-output/result.json'),
            whisper_version=whisper.__version__,torch_version=torch.__version__,cuda=torch.version.cuda,
            matmul_allow_tf32=torch.backends.cuda.matmul.allow_tf32,cudnn_allow_tf32=torch.backends.cudnn.allow_tf32,
            python_version=sys.version,inputs=inputs,forced_sequences=True,accuracy_measured=False,
            commands_executed=False,microphone_used=False,playback_used=False))
        assert sha(checkpoint)==previous['model_sha256']
        model=whisper.load_model(str(checkpoint),device='cuda')
        py_folder=a.output/'python-full';py_folder.mkdir();py=dict(rows=[],vocab=model.dims.n_vocab)
        with torch.no_grad():
            for index,case in enumerate(config['cases']):
                mel=torch.from_numpy(np.fromfile(a.output/case['mel'],dtype='<f4').reshape(128,3000)).cuda()
                for mode,dtype in [('fp16',torch.float16),('fp32',torch.float32)]:
                    features=model.encoder(mel.to(dtype).unsqueeze(0))
                    for number,plan in enumerate(case['plans']):
                        tokens=list(plan['prefix']);rows=[]
                        for target in plan['sequence']:
                            value=model.decoder(torch.tensor([tokens],device='cuda'),features)[0,-1,:].float().cpu().numpy()
                            rows.append(value);tokens.append(target)
                        name=f'{index}-{mode}-{number}.f32'
                        np.stack(rows).astype('<f4').tofile(py_folder/name)
                        py['rows'].append(dict(id=case['id'],mode=mode,plan=plan['name'],logits=name,
                            prefix=plan['prefix'],sequence=plan['sequence'],shape=[len(rows),model.dims.n_vocab]))
                write_json(py_folder/'partial.json',py)
                print(json.dumps(dict(python_completed=index+1,total=len(config['cases']))),flush=True)
        write_json(py_folder/'result.json',py)
        dummy=SimpleNamespace(is_multilingual=True,num_languages=100,
            dims=SimpleNamespace(n_text_ctx=448,n_audio_ctx=1500),decoder=SimpleNamespace(blocks=[]))
        sources=[]
        for label,result in cpp_runs.items():
            for row in result['rows']:
                for cache,key in [('cached','logits'),('full','full_logits')]:
                    sources.append((f'cpp_{label}_{row["mode"]}_{cache}',a.output/label/'cpp-output',row,key))
        for row in load(a.trial/'python-output/result.json')['rows']:
            sources.append((f'python_{row["mode"]}_cached',a.trial/'python-output',row,'logits'))
        for row in py['rows']:sources.append((f'python_{row["mode"]}_full',py_folder,row,'logits'))
        plans={(c['id'],p['name']):p for c in config['cases'] for p in c['plans']}
        scores=[];steps=[]
        for label,folder,row,key in sources:
            plan=plans[(row['id'],row['plan'])]
            assert row['prefix']==plan['prefix'] and row['sequence']==plan['sequence']
            values=np.fromfile(folder/row[key],dtype='<f4').reshape(row['shape'])
            assert np.all(np.isfinite(values))
            task=DecodingTask(dummy,DecodingOptions(language='ru',prompt=plan['prefix'][1:-3],beam_size=5))
            assert list(task.initial_tokens)==plan['prefix']
            targets=[]
            for index,target in enumerate(plan['sequence']):
                logits=torch.from_numpy(values[index:index+1].copy())
                tokens=torch.tensor([plan['prefix']+plan['sequence'][:index]])
                for filter in task.logit_filters:filter.apply(logits,tokens)
                distribution=torch.log_softmax(logits,dim=-1)[0]
                value=float(distribution[target]);assert np.isfinite(value)
                targets.append(value)
                steps.append(dict(engine=label,id=row['id'],plan=row['plan'],step=index,target=target,
                    logprob=value,top1=int(distribution.argmax())))
            total=float(np.sum(targets,dtype=np.float64));length=len(targets)-1
            scores.append(dict(engine=label,id=row['id'],plan=row['plan'],score=total/length,
                sum_logprobs=total,length=length,eot_logprob=targets[-1],text=plan['text'],
                correct=plan['correct'],saved_selected=plan['selected']))
        write_json(a.output/'scores.json',dict(scores=scores,steps=steps,accuracy_measured=False,
            cached_python_reused=True,actual_search_scores_reproduced=False,commands_executed=False))
        print(json.dumps(dict(score_rows=len(scores),step_rows=len(steps))),flush=True)
    finally:
        assert checkpoint.resolve().is_relative_to(a.output)
        checkpoint.unlink();checkpoint.parent.rmdir()


if __name__=='__main__':
    for stream in (sys.stdout,sys.stderr):stream.reconfigure(encoding='utf-8',errors='replace')
    main()
