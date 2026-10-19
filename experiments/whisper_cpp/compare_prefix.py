"""Compare raw logits with identical mel and forced tokens; never execute text."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from benchmark import ROOT, isolated, sha, write_json


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', type=Path, required=True)
    parser.add_argument('--ids', type=int, nargs='+', required=True)
    args = parser.parse_args()
    output, worker = args.output.resolve(), args.worker.resolve()
    if output.exists() or not output.is_relative_to(ROOT / 'reports') or not worker.is_relative_to(ROOT / 'reports'):
        parser.error('Use a new reports output and an experimental worker')
    if len(set(args.ids)) != len(args.ids) or not 1 <= len(args.ids) <= 32:
        parser.error('Choose 1–32 unique saved input IDs')
    corpus = ROOT / 'reports/whisper-cpp/corpus'
    cpp_old = {r['id']: r for r in load(ROOT / 'reports/whisper-trace/safe-on/result.json')['rows']}
    py_old = {r['id']: r for r in load(ROOT / 'reports/whisper-trace/python-trial/result.json')['rows']}
    assert all(i in cpp_old and i in py_old and not cpp_old[i]['gated'] for i in args.ids)
    output.mkdir(parents=True)
    checkpoint = output / 'model-input/large-v3-turbo.pt'
    checkpoint.parent.mkdir()
    shutil.copy2(ROOT / 'backend/data/models/whisper/large-v3-turbo.pt', checkpoint)
    try:
        isolated(corpus / 'source/backend')
        import numpy as np
        import torch
        import whisper
        from whisper.decoding import PyTorchInference
        torch.set_num_threads(8)
        tokenizer = whisper.tokenizer.get_tokenizer(multilingual=True, num_languages=100, language='ru', task='transcribe')
        cases, samples = [], []
        for index, id in enumerate(args.ids):
            cpp, py = cpp_old[id], py_old[id]
            assert sha(corpus / cpp['pcm']) == cpp['sha256']
            pcm = np.fromfile(corpus / cpp['pcm'], dtype='<f4')
            cpp_events = cpp['native_result']['decoder_trace']['events']
            py_events = py['decoder_trace']['events']
            cpp_prompt = next(e for e in cpp_events if e['kind'] == 'prompt')['prompt']
            py_prompt = next(e for e in py_events if e['kind'] == 'prompt')['prompt']
            post = next(e for e in cpp_events if e['kind'] == 'post_rank')
            cpp_seq = next(d for d in post['decoders'] if d['index'] == post['selected'])['ids']
            post = next(e for e in py_events if e['kind'] == 'post_rank')
            py_seq = post['groups'][0][post['selected'][0]]['ids']
            # Common input is the actual Python encoder window, rounded to fp16 then
            # stored as fp32. C++ receives exactly these rounded values too.
            mel = whisper.audio.log_mel_spectrogram(pcm, n_mels=128, padding=whisper.audio.N_SAMPLES)
            mel = whisper.audio.pad_or_trim(mel, whisper.audio.N_FRAMES).half().float().numpy().astype('<f4')
            mel.tofile(output / f'{index}-common-mel.f32')
            pcm.tofile(output / f'{index}-pcm.f32')
            sequences = [('cpp_selected', cpp_seq)]
            if py_seq != cpp_seq: sequences.append(('python_selected_first', py_seq))
            plans = []
            for prefix_name, prefix in [('cpp', cpp_prompt), ('python', py_prompt)]:
                for sequence_name, sequence in sequences:
                    # Include EOT for both replays, recording the same target sequence.
                    sequence = list(sequence)
                    if sequence[-1] != tokenizer.eot: sequence.append(tokenizer.eot)
                    plans.append(dict(name=prefix_name + ':' + sequence_name, prefix=prefix, sequence=sequence))
            cases.append(dict(id=id, pcm=f'{index}-pcm.f32', mel=f'{index}-common-mel.f32', n_mels=128, plans=plans))
            samples.append(dict(id=id, reference=cpp['reference'], cpp=cpp['heard'], python=py['heard'],
                condition=cpp['condition'], cpp_correct=cpp['correct'], pcm_sha256=cpp['sha256']))
        config = dict(protocol=1, cases=cases)
        write_json(output / 'config.json', config)
        provenance = dict(whisper_version=whisper.__version__, torch_version=torch.__version__,
            python_version=sys.version, model_sha256=sha(checkpoint), worker_sha256=sha(worker),
            ggml_sha256=sha(ROOT / 'reports/whisper-cpp/models/turbo/ggml-model.bin'),
            common_mel_precision='fp16-rounded-fp32', samples=samples,
            config_sha256=sha(output / 'config.json'), microphone_used=False,
            playback_used=False, commands_executed=False, forced_sequences=True)
        write_json(output / 'run.json', provenance)
        command = [str(worker), str(ROOT / 'reports/whisper-cpp/models/turbo/ggml-model.bin'),
            str(output / 'config.json'), 'gpu', '8', str(os.getpid())]
        with (output / 'cpp.log').open('w', encoding='utf-8') as log:
            env = dict(os.environ)
            if os.name == 'nt': env['PATH'] = 'C:/Windows/System32;C:/Windows'
            subprocess.run(command, cwd=output, stdout=log, stderr=subprocess.STDOUT,
                timeout=900, check=True, env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        print('C++ forced replay complete', flush=True)
        native = load(output / 'cpp-output/result.json')
        # Special-token labels differ ([_EOT_] vs <|endoftext|>); compare roles
        # explicitly and compare exact bytes for ordinary text tokens.
        assert native['eot'] == tokenizer.eot and native['sot'] == tokenizer.sot
        assert native['timestamp_begin'] == tokenizer.timestamp_begin
        assert all(tokenizer.encoding.decode_single_token_bytes(int(id)).hex() == value
            for id, value in native['vocabulary_hex'].items() if int(id) < tokenizer.eot)
        model = whisper.load_model(str(checkpoint), device='cuda')
        assert native['vocab'] == model.dims.n_vocab
        result = dict(vocab=model.dims.n_vocab, rows=[], text_vocabulary_matches=True, special_roles_match=True,
            gpu=torch.cuda.get_device_name(0), forced_sequences=True)
        py_output = output / 'python-output'
        py_output.mkdir()
        with torch.no_grad():
            for case_index, case in enumerate(cases):
                mel = torch.from_numpy(np.fromfile(output / case['mel'], dtype='<f4').reshape(128, 3000)).cuda()
                for precision, dtype in [('fp16', torch.float16), ('fp32', torch.float32)]:
                    features = model.encoder(mel.to(dtype).unsqueeze(0))
                    for plan_index, plan in enumerate(case['plans']):
                        tokens = torch.tensor([plan['prefix']], device='cuda')
                        inference = PyTorchInference(model, len(plan['prefix']))
                        rows = []
                        try:
                            for target in plan['sequence']:
                                logits = inference.logits(tokens, features)[:, -1, :].float()
                                rows.append(logits[0].cpu().numpy())
                                tokens = torch.cat([tokens, torch.tensor([[target]], device='cuda')], dim=-1)
                        finally:
                            inference.cleanup_caching()
                        full_logits = model.decoder(tokens[:, :-1], features)[:, -1, :].float()[0].cpu().numpy()
                        replay_delta = float(np.max(np.abs(full_logits - rows[-1])))
                        name = f'{case_index}-{precision}-{plan_index}.f32'
                        np.stack(rows).astype('<f4').tofile(py_output / name)
                        result['rows'].append(dict(id=case['id'], mode=precision, plan=plan['name'],
                            prefix=plan['prefix'], sequence=plan['sequence'], logits=name,
                            incremental_full_max_abs=replay_delta,
                            shape=[len(rows), model.dims.n_vocab]))
                write_json(py_output / 'partial.json', result)
                print(json.dumps(dict(python_done=case_index + 1, total=len(cases))), flush=True)
        write_json(py_output / 'result.json', result)
    finally:
        assert checkpoint.resolve().is_relative_to(output)
        checkpoint.unlink()
        checkpoint.parent.rmdir()


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    main()
