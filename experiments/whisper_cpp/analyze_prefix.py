"""Summarize saved forced replays; these are not recognition accuracy scores."""
import argparse
import html
import json
from pathlib import Path
from types import SimpleNamespace
import sys

from benchmark import ROOT, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trial', type=Path, required=True)
    args = parser.parse_args()
    root = args.trial.resolve()
    assert root.is_relative_to(ROOT / 'reports')
    import numpy as np
    import torch
    import whisper
    from whisper.decoding import DecodingTask, DecodingOptions
    torch.set_num_threads(8)
    def load(p): return json.loads(p.read_text(encoding='utf-8'))
    config, run = load(root / 'config.json'), load(root / 'run.json')
    cpp, py = load(root / 'cpp-output/result.json'), load(root / 'python-output/result.json')
    cpp_map = {(r['id'], r['mode'], r['plan']): r for r in cpp['rows']}
    py_map = {(r['id'], r['mode'], r['plan']): r for r in py['rows']}
    dummy = SimpleNamespace(is_multilingual=True, num_languages=100,
        dims=SimpleNamespace(n_text_ctx=448, n_audio_ctx=1500), decoder=SimpleNamespace(blocks=[]))
    def logits(engine, row):
        data = np.fromfile(root / (engine + '-output') / row['logits'], dtype='<f4')
        assert data.size == np.prod(row['shape']) and np.all(np.isfinite(data))
        return torch.from_numpy(data.reshape(row['shape']))
    def filtered(values, row):
        task = DecodingTask(dummy, DecodingOptions(language='ru', prompt=row['prefix'][1:-3], beam_size=5))
        assert list(task.initial_tokens) == row['prefix']
        result = values.clone()
        for step in range(result.shape[0]):
            tokens = torch.tensor([row['prefix'] + row['sequence'][:step]])
            for filter in task.logit_filters: filter.apply(result[step:step+1], tokens)
        return torch.log_softmax(result, dim=-1)
    def compare(a, b):
        la, lb = torch.log_softmax(a, dim=-1), torch.log_softmax(b, dim=-1)
        pa, pb = la.exp(), lb.exp()
        # Logits have an arbitrary additive offset: compare centered values too.
        centered = (a - a.mean(-1, keepdim=True)) - (b - b.mean(-1, keepdim=True))
        tv = ((pa - pb).abs().sum(-1) / 2).numpy()
        kl = (pa * (la - lb)).sum(-1).numpy()
        return dict(steps=a.shape[0], top1_equal=int((a.argmax(-1) == b.argmax(-1)).sum()),
            tv_median=float(np.median(tv)), tv_max=float(np.max(tv)),
            kl_median=float(np.median(kl)), centered_rmse=float(centered.square().mean().sqrt()),
            centered_max_abs=float(centered.abs().max()))
    all_steps, pairs, mel_stats, scores = [], [], [], []
    cache = {}
    for case_index, case in enumerate(config['cases']):
        pcm = np.fromfile(root / case['pcm'], dtype='<f4')
        original = whisper.audio.pad_or_trim(whisper.audio.log_mel_spectrogram(pcm,
            n_mels=128, padding=whisper.audio.N_SAMPLES), 3000).numpy()
        common = np.fromfile(root / case['mel'], dtype='<f4').reshape(128, 3000)
        native_row = cpp_map[(case['id'], 'common', case['plans'][0]['name'])]
        native = np.fromfile(root / 'cpp-output' / native_row['native_mel'], dtype='<f4').reshape(128, 3000)
        delta = native - original
        mel_stats.append(dict(id=case['id'], native_vs_python_rmse=float(np.sqrt(np.mean(delta**2))),
            native_vs_python_max_abs=float(np.max(np.abs(delta))),
            fp16_round_rmse=float(np.sqrt(np.mean((common-original)**2)))))
        for plan in case['plans']:
            rows = [('cpp_common', 'cpp', cpp_map[(case['id'], 'common', plan['name'])]),
                    ('cpp_native', 'cpp', cpp_map[(case['id'], 'native', plan['name'])]),
                    ('py_fp16', 'python', py_map[(case['id'], 'fp16', plan['name'])]),
                    ('py_fp32', 'python', py_map[(case['id'], 'fp32', plan['name'])])]
            arrays = {}
            probabilities = {}
            for name, engine, row in rows:
                assert row['prefix'] == plan['prefix'] and row['sequence'] == plan['sequence']
                arrays[name] = logits(engine, row)
                probabilities[name] = filtered(arrays[name], row)
                selected = probabilities[name][torch.arange(len(plan['sequence'])), plan['sequence']]
                scores.append(dict(id=case['id'], plan=plan['name'], engine=name,
                    finite=bool(torch.isfinite(selected).all()),
                    mean_common_filtered_logprob=float(selected.mean()) if torch.isfinite(selected).all() else None))
            for left, right, label in [('py_fp16', 'cpp_common', 'shared_mel_fp16_vs_cpp'),
                    ('py_fp32', 'cpp_common', 'shared_mel_fp32_vs_cpp'),
                    ('cpp_common', 'cpp_native', 'cpp_mel_change'),
                    ('py_fp16', 'py_fp32', 'python_precision_change')]:
                raw = compare(arrays[left], arrays[right])
                a, b = probabilities[left], probabilities[right]
                tv = (a.exp() - b.exp()).abs().sum(-1) / 2
                top1 = a.argmax(-1) == b.argmax(-1)
                for step in range(len(plan['sequence'])):
                    target = plan['sequence'][step]
                    va, vb = float(a[step, target]), float(b[step, target])
                    all_steps.append(dict(id=case['id'], plan=plan['name'], comparison=label, step=step,
                        target=target, filtered_tv=float(tv[step]), top1_equal=bool(top1[step]),
                        target_logprob_delta=va-vb if np.isfinite(va) and np.isfinite(vb) else None))
                pairs.append(dict(id=case['id'], plan=plan['name'], comparison=label, raw=raw,
                    filtered_tv_median=float(tv.median()), filtered_top1_equal=int(top1.sum())))
    aggregate = {}
    for label in sorted(set(r['comparison'] for r in all_steps)):
        rows = [r for r in all_steps if r['comparison'] == label]
        deltas = [abs(r['target_logprob_delta']) for r in rows if r['target_logprob_delta'] is not None]
        aggregate[label] = dict(steps=len(rows), filtered_top1_equal=sum(r['top1_equal'] for r in rows),
            filtered_tv_median=float(np.median([r['filtered_tv'] for r in rows])),
            filtered_tv_max=float(np.max([r['filtered_tv'] for r in rows])),
            target_logprob_delta_abs_median=float(np.median(deltas)), finite_target_pairs=len(deltas))
    prompt_effect, preferences = [], []
    tokenizer = whisper.tokenizer.get_tokenizer(True,num_languages=100,language='ru',task='transcribe')
    first_case = config['cases'][0]
    cpp_prompt = first_case['plans'][0]['prefix'][1:-3]
    py_prompt = next(p['prefix'][1:-3] for p in first_case['plans'] if p['name'].startswith('python:'))
    prompt_text = b''.join(bytes.fromhex(cpp['vocabulary_hex'][str(i)]) for i in cpp_prompt).decode('utf-8')
    py_plain = tokenizer.encode(prompt_text)
    tokenization = dict(cpp_count=len(cpp_prompt), python_same_text_count=len(py_plain),
        python_with_leading_space_count=len(py_prompt),
        cpp_equal_python_same_text=cpp_prompt==py_plain,
        python_prompt_is_space_plus_same_text=tokenizer.decode(py_prompt)==' '+prompt_text.strip())
    for case in config['cases']:
        sequences = sorted(set(p['name'].split(':', 1)[1] for p in case['plans']))
        for sequence_name in sequences:
            for engine, mode in [('cpp', 'common'), ('python', 'fp16')]:
                source = cpp_map if engine == 'cpp' else py_map
                left = source[(case['id'], mode, 'cpp:' + sequence_name)]
                right = source[(case['id'], mode, 'python:' + sequence_name)]
                a, b = filtered(logits(engine,left),left), filtered(logits(engine,right),right)
                prompt_effect.append(dict(id=case['id'], engine=engine, sequence=sequence_name,
                    steps=a.shape[0], top1_equal=int((a.argmax(-1)==b.argmax(-1)).sum()),
                    tv_median=float(((a.exp()-b.exp()).abs().sum(-1)/2).median())))
        if len(sequences) == 2:
            for prefix in ('cpp', 'python'):
                for engine in ('cpp_common','py_fp16','py_fp32'):
                    group = [r for r in scores if r['id']==case['id'] and r['engine']==engine
                        and r['plan'].startswith(prefix + ':')]
                    first = next(r for r in group if r['plan'].endswith(':cpp_selected'))
                    second = next(r for r in group if r['plan'].endswith(':python_selected_first'))
                    if first['finite'] and second['finite']:
                        preferences.append(dict(id=case['id'], prefix=prefix, engine=engine,
                            python_minus_cpp=second['mean_common_filtered_logprob']-first['mean_common_filtered_logprob']))
    result = dict(cases=len(config['cases']), cpp_replays=len(cpp['rows']), python_replays=len(py['rows']),
        aggregate=aggregate, pairs=pairs, steps=all_steps, scores=scores, mel=mel_stats,
        prompt_effect=prompt_effect, candidate_preferences=preferences,
        tokenization=tokenization,
        cpp_incremental_full_max_abs=max(r['incremental_full_max_abs'] for r in cpp['rows']),
        python_incremental_full_max_abs=max(r['incremental_full_max_abs'] for r in py['rows']),
        forced_sequences=True, accuracy_measured=False, common_filters='installed Python DecodingTask defaults',
        samples=run['samples'])
    write_json(root.parent / 'summary.json', result)
    table = ''.join(f'<tr><td>{html.escape(k)}</td><td>{v["filtered_top1_equal"]}/{v["steps"]}</td>'
        f'<td>{v["filtered_tv_median"]:.6g}</td><td>{v["target_logprob_delta_abs_median"]:.6g}</td></tr>' for k,v in aggregate.items())
    samples = ''.join(f'<tr><td>{r["id"]}</td><td>{html.escape(r["reference"])}</td>'
        f'<td>{html.escape(r["cpp"])}</td><td>{html.escape(r["python"])}</td></tr>' for r in run['samples'])
    page = f'''<!doctype html><html lang="ru"><meta charset="utf-8"><title>Scott: одинаковые токены</title>
<style>body{{font:16px system-ui;background:#101827;color:#e5edf7;max-width:1150px;margin:40px auto;padding:0 20px}}
table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{padding:10px;border-bottom:1px solid #334155;text-align:left}}a{{color:#8ac4ff}}</style>
<h1>Whisper: одинаковый вход и токены</h1><p>{len(config['cases'])} сохранённых записей. Каждый движок получает
одинаковую спектрограмму и заданную последовательность токенов. Поиск кандидатов здесь отключён.</p>
<p>Все распределения ниже обработаны одинаковыми фильтрами Python. TV — расстояние распределений
от 0 (совпадают) до 1. Эти значения не являются точностью распознавания.</p>
<table><tr><th>Сравнение</th><th>Совпадение первого токена</th><th>Медиана TV</th><th>Медиана |Δ logprob цели|</th></tr>{table}</table>
<h2>Записи: прежние ответы для контекста</h2><table><tr><th>ID</th><th>Исходная реплика</th><th>C++</th><th>Python</th></tr>{samples}</table>
<p>Повторы с полным префиксом проверяют позиции кеша. Максимальное отличие logits:
C++ {result['cpp_incremental_full_max_abs']:.6g}, Python {result['python_incremental_full_max_abs']:.6g}.</p>
<p><a href="summary.json">Подробные числа</a> · <a href="README.md">Выводы и ограничения</a> ·
<a href="{root.name}/run.json">Версии и SHA256</a></p></html>'''
    (root.parent / 'index.html').write_text(page, encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('cases','cpp_replays','python_replays','aggregate',
        'cpp_incremental_full_max_abs','python_incremental_full_max_abs')}, ensure_ascii=False))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
