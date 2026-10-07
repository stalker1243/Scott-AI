"""Recognize saved comparison WAVs and render a manual listening report."""
from collections import defaultdict
from html import escape
from pathlib import Path
import argparse
import json
import shutil
import statistics
import threading
import time

from trial_utils import ROOT,save_json
from benchmark_base import Backend
from check_streaming import protected
from scott_voice_process import checksum


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'reports/voice-stream-speed')
    parser.add_argument('--render-only',action='store_true')
    args=parser.parse_args();folder=args.output
    files=[folder/'speed.json',folder/'reverse/speed.json']
    reports=[json.loads(path.read_text(encoding='utf-8')) for path in files]
    rows=[]
    for index,report in enumerate(reports):
        for row in report['results']:
            row=dict(row)
            for key in ('complete','joined','timed'):
                row[key]=('reverse/' if index else '')+row[key]
            row['comparison']='ABBA' if index==0 else 'BA'
            assert checksum(folder/row['complete'])==row['complete_sha256']
            rows.append(row)
    validation_path=folder/'validation.json'
    if args.render_only:
        validation=json.loads(validation_path.read_text(encoding='utf-8'))
    else:
        before=protected();backend=Backend('http://127.0.0.1:8000')
        stop=threading.Event();health=[];errors=[]
        def monitor():
            while not stop.is_set():
                try:
                    _,elapsed=backend.get('/health',timeout=3);health.append(elapsed)
                except Exception as error: errors.append(type(error).__name__)
                stop.wait(.15)
        thread=threading.Thread(target=monitor,daemon=True);thread.start()
        validation=dict(results=[],unique_requests=0);heard={}
        try:
            for row in rows:
                item=dict(comparison=row['comparison'],run=row['run'],case=row['id'],mode=row['mode'],recognition={})
                for kind in ('complete','joined'):
                    path=folder/row[kind];key=(checksum(path),row['text'])
                    reused=key in heard
                    if not reused:
                        heard[key]=backend.transcribe(path,row['text']);validation['unique_requests']+=1
                    item['recognition'][kind]=dict(**heard[key],reused_identical_wav=reused,sha256=key[0])
                validation['results'].append(item)
                print(json.dumps(dict(comparison=item['comparison'],run=item['run'],case=item['case'],
                    wer={k:v['word_error_rate'] for k,v in item['recognition'].items()})),flush=True)
        finally:
            stop.set();thread.join(timeout=4)
            validation['health']=dict(requests=len(health),errors=errors,max_seconds=round(max(health),4) if health else None)
            validation['protected_files_unchanged']=before==protected()
            save_json(validation_path,validation)
    assert validation['protected_files_unchanged'] and not validation['health']['errors']
    assert len(validation['results'])==len(rows)
    assert all(v['success'] and v['word_error_rate']==0 for row in validation['results'] for v in row['recognition'].values())
    assert all(report['protected_files_unchanged'] for report in reports)
    groups=defaultdict(list)
    for row in rows: groups[(row['mode'],row['id'])].append(row)
    summary=[];table=[]
    for case in ('status','technical','numbers'):
        original,fast=groups[('original',case)],groups[('accelerated',case)]
        entry=dict(case=case,title=original[0]['title'],cold=case=='status',modes={})
        cells=[]
        for name,data in (('original',original),('accelerated',fast)):
            values={key:[r[key] for r in data] for key in ('first_audio_seconds','total_seconds','real_time_factor')}
            values['gap_seconds']=[r['schedule']['gap_seconds'] for r in data]
            stats={key:dict(median=statistics.median(v),minimum=min(v),maximum=max(v)) for key,v in values.items()}
            entry['modes'][name]=stats
            first=stats['first_audio_seconds'];total=stats['total_seconds'];gaps=stats['gap_seconds']
            cells.append(f'<td>{first["median"]:.2f} с<small>{first["minimum"]:.2f}–{first["maximum"]:.2f}</small></td>'
                f'<td>{total["median"]:.2f} с<small>{total["minimum"]:.2f}–{total["maximum"]:.2f}</small></td>'
                f'<td>{gaps["median"]:.2f} с<small>{gaps["minimum"]:.2f}–{gaps["maximum"]:.2f}</small></td>')
        summary.append(entry)
        table.append(f'<tr><td>{escape(entry["title"])}<small>{"Холодный запуск" if entry["cold"] else "Разогретая модель"}</small></td>'+''.join(cells)+'</tr>')
    cards=[]
    # BA is the most recent matched pair; preserve every individual measurement below.
    for case in ('status','technical','numbers'):
        pair=[next(row for row in rows if row['comparison']=='BA' and row['id']==case and row['mode']==mode)
            for mode in ('original','accelerated')]
        players=[]
        for row,label in zip(pair,('Обычный','Ускоренный')):
            players.append(f'<div><h3>{label}</h3><p>{row["first_audio_seconds"]:.2f} с до первого блока · '
                f'{row["total_seconds"]:.2f} с синтеза</p><h4>Поток с измеренными паузами</h4>'
                f'<audio controls preload="none" src="{escape(row["timed"],quote=True)}"></audio>'
                f'<details><summary>Полный WAV и стыки потока</summary><h4>Полный WAV</h4>'
                f'<audio controls preload="none" src="{escape(row["complete"],quote=True)}"></audio><h4>Соединённые блоки</h4>'
                f'<audio controls preload="none" src="{escape(row["joined"],quote=True)}"></audio></details></div>')
        cards.append(f'<section><h2>{escape(pair[0]["title"])}</h2><p>{escape(pair[0]["text"])}</p><div class="grid">'+''.join(players)+'</div></section>')
    all_rows=''.join(f'<tr><td>{row["comparison"]} · {row["run"]}</td><td>{"Обычный" if row["mode"]=="original" else "Ускоренный"}</td>'
        f'<td>{escape(row["title"])}</td><td>{row["first_audio_seconds"]:.2f} с</td><td>{row["total_seconds"]:.2f} с</td>'
        f'<td>{row["audio_seconds"]:.2f} с</td><td>{row["schedule"]["gap_seconds"]:.2f} с</td><td>{row["real_time_factor"]:.2f}</td></tr>' for row in rows)
    settings=folder/'settings';settings.mkdir(exist_ok=True);images=[]
    for name in ('classic','glass-preparing','terminal-compact'):
        source=ROOT/f'ScottAI_qt/build/screenshots/voice/{name}.png'
        if source.is_file():
            shutil.copyfile(source,settings/(name+'.png'))
            images.append(f'<img loading="lazy" src="settings/{name}.png" alt="Настройки: {name}">')
    document='''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Scott Voice — ускорение потока</title><style>
*{box-sizing:border-box}body{margin:0;background:#10141b;color:#eef2f8;font:16px/1.55 system-ui,sans-serif}main{max-width:1150px;margin:auto;padding:42px 24px}
h1{font-size:34px;line-height:1.2}h2{font-size:22px}h3{color:#73ceb5}h4{font-size:14px;font-weight:500}p,small{color:#b9c5d6}small{display:block;font-size:12px}.eyebrow,a,summary{color:#73ceb5}.grid{display:grid;grid-template-columns:1fr 1fr;gap:24px}
section{padding:22px;background:#19202b;border:1px solid #303d50;border-radius:16px;margin:22px 0}audio{width:100%}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;min-width:880px}th,td{padding:12px 9px;border-bottom:1px solid #303d50;text-align:left;vertical-align:top}th{font-size:13px;color:#73ceb5}details{margin:15px 0}summary{cursor:pointer}.note{border-left:3px solid #73ceb5;padding-left:16px}img{width:100%;border-radius:12px;margin:12px 0}@media(max-width:700px){.grid{grid-template-columns:1fr}main{padding:26px 16px}}
</style><main><div class="eyebrow">SCOTT VOICE · RTX 3060 · 7 ОКТЯБРЯ 2026</div><h1>Ускоренный синтез и паузы</h1>
<p>Ускорение встроено в настройки Qt отдельным экспериментальным переключателем. По умолчанию выключено; включение сохраняется между запусками.</p>
<p class="note">Способ вычислений меняет запись: тембр и ударения нужно оценить на слух. Принятый эталон сохраняется. Генерация пока медленнее речи, паузы остаются.</p>
<h2>Три замера каждого режима</h2><p>Медиана и диапазон. Отдельные процессы и пустые кеши, порядок ABBA, затем BA. STT выполнялся после всех замеров. На этой машине время обычного синтеза заметно менялось; эти данные не гарантируют фиксированный процент ускорения.</p>
<div class="scroll"><table><thead><tr><th>Фраза</th><th colspan="3">Обычный: первый блок / весь синтез / паузы</th><th colspan="3">Ускоренный: первый блок / весь синтез / паузы</th></tr></thead><tbody>'''
    document+=''.join(table)+'</tbody></table></div><p>Время до первого WAV включает холодную загрузку для короткой фразы. Акустическая задержка устройства не измерялась. '
    document+='В записи потока начальное ожидание не включено; вставлены измеренные паузы между блоками.</p>'+''.join(cards)
    document+=f'<p>Проверено {len(rows)*2} WAV через Whisper; {validation["unique_requests"]} разных записей отправлено в STT, '
    document+='результаты побайтово одинаковых повторов использованы повторно. Ошибок слов нет. Слова проверяет STT; характер голоса оценивается на слух.</p>'
    document+=f'<p>Отмена ускоренного потока: {reports[0]["cancel"]["seconds"]:.3f} с. Полные исходные WAV совпали с принятыми образцами. '
    document+='Модель, эталон, четыре CPU-потока и BF16/SDPA сохранены; изменяется только RMSNorm. Настройки и история в измерениях не переключались.</p>'
    document+='<details><summary>Все измерения</summary><div class="scroll"><table><thead><tr><th>Прогон</th><th>Режим</th><th>Фраза</th><th>Первый блок</th><th>Синтез</th><th>Речь</th><th>Паузы</th><th>RTF</th></tr></thead><tbody>'+all_rows+'</tbody></table></div></details>'
    document+='<section><h2>Настройка в Qt</h2><p>Проверочные снимки с включёнными экспериментальными режимами. Рабочие настройки пользователя сохранены.</p>'+''.join(images)+'</section>'
    document+='<p><a href="speed.json">ABBA</a> · <a href="reverse/speed.json">BA</a> · <a href="validation.json">STT и контрольные суммы</a>. '
    document+='<a href="https://docs.pytorch.org/docs/2.9/generated/torch.nn.functional.rms_norm.html">Используемая функция PyTorch RMSNorm</a>.</p></main>'
    document+='''<script>document.querySelectorAll('audio').forEach(p=>p.addEventListener('play',()=>document.querySelectorAll('audio').forEach(q=>{if(q!==p)q.pause()})));</script></html>'''
    (folder/'index.html').write_text(document,encoding='utf-8')
    save_json(folder/'summary.json',dict(cases=summary,wavs=len(rows)*2,unique_stt_requests=validation['unique_requests'],
        health=validation['health'],cancel=reports[0]['cancel'],protected_files_unchanged=validation['protected_files_unchanged']))
    print(json.dumps(dict(wavs=len(rows)*2,unique_stt_requests=validation['unique_requests'],health=validation['health'])))


if __name__=='__main__': main()
