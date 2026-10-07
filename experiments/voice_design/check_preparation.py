"""Compare cold and manually prepared workers; synthetic files only, no audio input/output."""
from dataclasses import replace
from pathlib import Path
import argparse
import hashlib
import html
import json
import shutil
import sys
import time

from check_streaming import protected
from trial_utils import ROOT, cases, save_json
from scott_voice_engine import default_config, inspect_installation
from scott_voice_process import ScottVoiceProcess


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'reports/voice-preparation/trial')
    args=parser.parse_args()
    folder=args.output
    if (folder/'preparation.json').exists():
        parser.error('Choose a new --output directory')
    folder.mkdir(parents=True,exist_ok=True)
    before=protected()
    case=next(c for c in cases() if c['id']=='status')
    accepted=ROOT/'reports/voice-base/base-status.wav'
    expected=hashlib.sha256(accepted.read_bytes()).hexdigest()
    report=dict(protected_sha256=before,device='cuda',rms_norm=False,
        microphone_opened=False,audio_output_opened=False,new_synthesis=True,
        accepted_sha256=expected,results=[])
    for run,mode in enumerate(['cold','prepared','prepared','cold'],1):
        config=replace(default_config(),cache_dir=folder/f'{run}-{mode}-cache')
        assert config.device=='cuda' and not config.rms_norm
        assert not inspect_installation(config)
        with ScottVoiceProcess(config,timeout=180,idle_timeout=0) as client:
            loaded=None
            if mode=='prepared':
                start=time.perf_counter()
                state=client.prepare()
                loaded=time.perf_counter()-start
                assert state['model_loaded'] and not list(config.cache_dir.glob('*.wav'))
            start=time.perf_counter()
            audio=client.synthesize(case['text'],'natural')
            elapsed=time.perf_counter()-start
            assert not audio.cached and client.status()['model_loaded']
            target=folder/f'{run}-{mode}.wav'
            shutil.copyfile(audio.path,target)
            actual=hashlib.sha256(target.read_bytes()).hexdigest()
            assert actual==expected, 'Prepared voice differs from accepted sample'
            row=dict(run=run,mode=mode,preparation_seconds=loaded,
                response_seconds=elapsed,total_seconds=elapsed+(loaded or 0),
                audio_seconds=audio.seconds,sha256=actual,accepted_pcm_equal=True,audio=target.name)
            report['results'].append(row)
            save_json(folder/'preparation.json',report)
            print(json.dumps(row),flush=True)
        assert not client.status()['running'] and not list(config.cache_dir.glob('.pending-*'))
    report['protected_files_unchanged']=protected()==before
    assert report['protected_files_unchanged']
    save_json(folder/'preparation.json',report)
    rows=''.join(f'<tr><td>{r["run"]}</td><td>{"Подготовленный" if r["mode"]=="prepared" else "Холодный"}</td>'
        f'<td>{r["preparation_seconds"]:.2f}</td><td>{r["response_seconds"]:.2f}</td><td>{r["total_seconds"]:.2f}</td></tr>'
        if r['preparation_seconds'] is not None else
        f'<tr><td>{r["run"]}</td><td>Холодный</td><td>—</td><td>{r["response_seconds"]:.2f}</td><td>{r["total_seconds"]:.2f}</td></tr>'
        for r in report['results'])
    document=f'''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Scott Voice — подготовка модели</title><style>body{{background:#10141b;color:#eef2f8;font:16px/1.6 system-ui;margin:0}}main{{max-width:1000px;margin:auto;padding:40px 24px}}p{{color:#bdc9d8}}a,th{{color:#73ceb5}}table{{border-collapse:collapse;width:100%;min-width:720px}}td,th{{padding:12px 8px;text-align:left;border-bottom:1px solid #344153}}.scroll{{overflow:auto}}audio{{width:min(100%,500px)}}</style>
<main><h1>Подготовка Scott Voice перед разговором</h1><p>Модель и опора голоса загружаются заранее по кнопке «Подготовить к речи». Это переносит работу до первого вопроса. Параметры генерации и принятый тембр сохраняются.</p>
<p>RTX 3060 · обычные вычисления · четыре отдельных работника в порядке холодный / подготовленный / подготовленный / холодный. Во всех случаях кеш ответа пуст. Синтетическая фраза: {html.escape(case['text'])}</p>
<div class="scroll"><table><thead><tr><th>Прогон</th><th>Работник</th><th>Подготовка, с</th><th>После запроса, с</th><th>Вся работа, с</th></tr></thead><tbody>{rows}</tbody></table></div>
<p>Подготовка не ускоряет саму генерацию и расходует видеопамять до первого вопроса. Без запросов работник освобождается через две минуты; кнопка «Освободить модель» отменяет его сразу. Время зависит от загрузки машины и файлового кеша.</p>
<p>Все четыре WAV совпали с принятым образцом по SHA256. Повторное распознавание одинаковых файлов не выполнялось. Микрофон, команды, проигрывание и рабочий backend не запускались; настройки сохранены.</p>
<h2>Принятый голос после подготовки</h2><audio controls preload="none" src="2-prepared.wav"></audio>
<p><a href="preparation.json">Исходные измерения</a> · <a href="../../voice-device/index.html">Проверка вывода звука</a></p></main></html>'''
    (folder/'index.html').write_text(document,encoding='utf-8')


if __name__=='__main__':
    main()
