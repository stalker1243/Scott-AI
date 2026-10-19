"""Replay complete saved candidates with common mel/prefix and identical filters."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

from benchmark import ROOT, isolated, sha, write_json


def load(path, limit=128*1024*1024):
    path = path.resolve()
    if not path.is_relative_to(ROOT/'reports') or not path.is_file() or path.stat().st_size > limit:
        raise ValueError('Use a bounded saved report')
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('output', 'worker', 'pool', 'audit'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--ids', type=int, nargs='+', required=True)
    a = p.parse_args()
    for name in ('output', 'worker', 'pool', 'audit'):
        setattr(a, name, getattr(a, name).resolve())
    if a.output.exists() or not a.output.is_relative_to(ROOT/'reports') or not a.worker.is_relative_to(ROOT/'reports'):
        p.error('Use a new report directory and experimental worker')
    if len(set(a.ids)) != len(a.ids) or not 1 <= len(a.ids) <= 32:
        p.error('Choose 1–32 unique saved IDs')
    pool = load(a.pool)
    rows = {r['id']: r for r in pool['rows']}
    audits = {r['id']: r for r in load(a.audit)['rows'] if r['name'] == 'pool-exact'}
    corpus = ROOT/'reports/whisper-cpp/corpus'
    specifications = []
    for id in a.ids:
        row, audit = rows[id], audits[id]
        assert not row['gated'] and not row['correct'] and audit['correct_candidate_present']
        assert sha(corpus/row['pcm']) == row['sha256']
        trace = row['native_result']['decoder_trace']; assert trace['complete']
        prompts = [e for e in trace['events'] if e['kind'] == 'prompt']
        ranks = [e for e in trace['events'] if e['kind'] == 'pool_rank']
        selections = [e for e in trace['events'] if e['kind'] == 'pool_select']
        # Five genuine EOT candidates: do not mix synthetic finalization here.
        assert len(prompts) == len(ranks) == 1 and prompts[0]['temperature'] == 0
        assert selections[-1]['finished_count'] == 5
        candidates = ranks[0]['candidates']; assert len(candidates) == len(audit['candidates']) == 5
        plans = []
        for index, (candidate, judged) in enumerate(zip(candidates, audit['candidates'])):
            text = b''.join(bytes.fromhex(trace['vocabulary_hex'][str(id)]) for id in candidate['ids'] if id < 50257).decode('utf-8')
            assert text.strip() == judged['text']
            sequence = list(candidate['ids']) + [50257]
            assert 2 <= len(sequence) <= 96 and 50257 not in sequence[:-1]
            assert len(prompts[0]['prompt']) + len(sequence) <= 448
            plans.append(dict(name=str(index), prefix=prompts[0]['prompt'], sequence=sequence,
                text=judged['text'], correct=judged['correct'], failed=candidate['failed'],
                selected=index == ranks[0]['selected'], saved_score=candidate['score'],
                saved_sum=candidate['sum_logprobs_all'], sampled_eot=True))
        specifications.append(dict(id=id, reference=row['reference'], condition=row['condition'],
            pcm=row['pcm'], pcm_sha256=row['sha256'], plans=plans))
    a.output.mkdir(parents=True)
    checkpoint = a.output/'model-input/large-v3-turbo.pt'; checkpoint.parent.mkdir()
    shutil.copy2(ROOT/'backend/data/models/whisper/large-v3-turbo.pt', checkpoint)
    try:
        isolated(corpus/'source/backend')
        import numpy as np
        import torch
        import whisper
        from whisper.decoding import DecodingTask, DecodingOptions, PyTorchInference
        torch.set_num_threads(8)
        cases = []
        for index, spec in enumerate(specifications):
            pcm = np.fromfile(corpus/spec['pcm'], dtype='<f4')
            mel = whisper.audio.pad_or_trim(whisper.audio.log_mel_spectrogram(pcm,
                n_mels=128, padding=whisper.audio.N_SAMPLES), 3000).half().float().numpy()
            pcm.astype('<f4').tofile(a.output/f'{index}-pcm.f32')
            mel.astype('<f4').tofile(a.output/f'{index}-mel.f32')
            cases.append(dict(id=spec['id'], pcm=f'{index}-pcm.f32', mel=f'{index}-mel.f32',
                n_mels=128, plans=spec['plans']))
        write_json(a.output/'config.json', dict(protocol=1, cases=cases))
        write_json(a.output/'run.json', dict(whisper_version=whisper.__version__, torch_version=torch.__version__,
            python_version=sys.version, model_sha256=sha(checkpoint), worker_sha256=sha(a.worker),
            ggml_sha256=sha(ROOT/'reports/whisper-cpp/models/turbo/ggml-model.bin'),
            pool_sha256=sha(a.pool), audit_sha256=sha(a.audit), config_sha256=sha(a.output/'config.json'),
            common_mel_precision='fp16-rounded-fp32', samples=specifications,
            microphone_used=False, playback_used=False, commands_executed=False, forced_sequences=True))
        env = dict(os.environ)
        if os.name == 'nt': env['PATH'] = 'C:/Windows/System32;C:/Windows'
        with (a.output/'cpp.log').open('w', encoding='utf-8') as log:
            subprocess.run([str(a.worker), str(ROOT/'reports/whisper-cpp/models/turbo/ggml-model.bin'),
                str(a.output/'config.json'), 'gpu', '8', str(os.getpid())], cwd=a.output,
                stdout=log, stderr=subprocess.STDOUT, check=True, timeout=900, env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        print('C++ candidate replay complete', flush=True)
        cpp = load(a.output/'cpp-output/result.json')
        tokenizer = whisper.tokenizer.get_tokenizer(True, num_languages=100, language='ru', task='transcribe')
        assert cpp['eot'] == tokenizer.eot and cpp['timestamp_begin'] == tokenizer.timestamp_begin
        assert all(tokenizer.encoding.decode_single_token_bytes(int(id)).hex() == text
            for id, text in cpp['vocabulary_hex'].items() if int(id) < tokenizer.eot)
        model = whisper.load_model(str(checkpoint), device='cuda')
        assert model.dims.n_vocab == cpp['vocab']
        py_output = a.output/'python-output'; py_output.mkdir()
        py = dict(vocab=cpp['vocab'], rows=[], gpu=torch.cuda.get_device_name(0), forced_sequences=True)
        with torch.no_grad():
            for case_index, case in enumerate(cases):
                mel = torch.from_numpy(np.fromfile(a.output/case['mel'], dtype='<f4').reshape(128,3000)).cuda()
                for precision, dtype in [('fp16',torch.float16), ('fp32',torch.float32)]:
                    features = model.encoder(mel.to(dtype).unsqueeze(0))
                    for plan_index, plan in enumerate(case['plans']):
                        tokens = torch.tensor([plan['prefix']],device='cuda')
                        inference = PyTorchInference(model,len(plan['prefix'])); logits = []
                        try:
                            for target in plan['sequence']:
                                values = inference.logits(tokens,features)[:,-1,:].float()
                                logits.append(values[0].cpu().numpy())
                                tokens = torch.cat([tokens,torch.tensor([[target]],device='cuda')],dim=-1)
                        finally:
                            inference.cleanup_caching()
                        full = model.decoder(tokens[:,:-1],features)[:,-1,:].float()[0].cpu().numpy()
                        name = f'{case_index}-{precision}-{plan_index}.f32'
                        np.stack(logits).astype('<f4').tofile(py_output/name)
                        py['rows'].append(dict(id=case['id'],mode=precision,plan=plan['name'],
                            prefix=plan['prefix'],sequence=plan['sequence'],logits=name,
                            incremental_full_max_abs=float(np.max(np.abs(full-logits[-1]))),
                            shape=[len(logits),cpp['vocab']]))
                write_json(py_output/'partial.json',py)
                print(json.dumps(dict(python_done=case_index+1,total=len(cases))),flush=True)
        write_json(py_output/'result.json',py)
        # Same official Python filters on every raw replay; scores include all
        # generated timestamps and genuine EOT, excluding prompt from length.
        dummy = SimpleNamespace(is_multilingual=True,num_languages=100,
            dims=SimpleNamespace(n_text_ctx=448,n_audio_ctx=1500),decoder=SimpleNamespace(blocks=[]))
        cpp_map = {(r['id'],r['mode'],r['plan']):r for r in cpp['rows']}
        py_map = {(r['id'],r['mode'],r['plan']):r for r in py['rows']}
        scores,steps,preferences = [],[],[]
        for case in cases:
            for plan in case['plans']:
                for label,engine,mode,mapping in [('cpp_common','cpp','common',cpp_map),
                    ('cpp_native','cpp','native',cpp_map),('python_fp16','python','fp16',py_map),
                    ('python_fp32','python','fp32',py_map)]:
                    row=mapping[(case['id'],mode,plan['name'])]
                    assert row['prefix']==plan['prefix'] and row['sequence']==plan['sequence']
                    values=np.fromfile(a.output/(engine+'-output')/row['logits'],dtype='<f4').reshape(row['shape'])
                    assert np.all(np.isfinite(values))
                    task=DecodingTask(dummy,DecodingOptions(language='ru',prompt=plan['prefix'][1:-3],beam_size=5))
                    assert list(task.initial_tokens)==plan['prefix']
                    targets=[]
                    for index,target in enumerate(plan['sequence']):
                        logits=torch.from_numpy(values[index:index+1].copy())
                        tokens=torch.tensor([plan['prefix']+plan['sequence'][:index]])
                        for filter in task.logit_filters:filter.apply(logits,tokens)
                        distribution=torch.log_softmax(logits,dim=-1)[0]
                        value=float(distribution[target]); assert np.isfinite(value)
                        targets.append(value)
                        steps.append(dict(id=case['id'],plan=plan['name'],engine=label,step=index,
                            target=target,logprob=value,top1=int(distribution.argmax())))
                    total=float(np.sum(targets,dtype=np.float64));length=len(targets)-1
                    ts=sum(v for id,v in zip(plan['sequence'],targets) if id>=tokenizer.timestamp_begin)
                    text=sum(v for id,v in zip(plan['sequence'],targets) if id<tokenizer.eot)
                    scores.append(dict(id=case['id'],plan=plan['name'],engine=label,text=plan['text'],
                        correct=plan['correct'],selected=plan['selected'],saved_score=plan['saved_score'],
                        length=length,sum_logprobs=total,score=total/length,avg_logprob=total/(length+1),
                        eot_logprob=targets[-1],timestamp_logprobs=ts,text_logprobs=text,
                        score_without_eot=(total-targets[-1])/length,incremental_full_max_abs=row['incremental_full_max_abs']))
            for label in ('cpp_common','cpp_native','python_fp16','python_fp32'):
                group=[s for s in scores if s['id']==case['id'] and s['engine']==label]
                winner=max(group,key=lambda s:s['score']);right=max((s for s in group if s['correct']),key=lambda s:s['score'])
                saved=next(s for s in group if s['selected'])
                preferences.append(dict(id=case['id'],engine=label,winner=winner['plan'],winner_correct=winner['correct'],
                    best_correct=right['plan'],saved_winner=saved['plan'],
                    correct_minus_saved=right['score']-saved['score'],winner_text=winner['text']))
        write_json(a.output/'scores.json',dict(scores=scores,steps=steps,preferences=preferences,
            cpp_replays=len(cpp['rows']),python_replays=len(py['rows']),cases=len(cases),plans=sum(len(c['plans']) for c in cases),
            filters='official Python DecodingTask, identical on each replay',accuracy_measured=False,
            actual_search_scores_reproduced=False,commands_executed=False))
        print(json.dumps(dict(cases=len(cases),cpp_replays=len(cpp['rows']),python_replays=len(py['rows']))),flush=True)
    finally:
        assert checkpoint.resolve().is_relative_to(a.output)
        checkpoint.unlink(); checkpoint.parent.rmdir()


if __name__=='__main__':
    for stream in (sys.stdout,sys.stderr):stream.reconfigure(encoding='utf-8',errors='replace')
    main()
