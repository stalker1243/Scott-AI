"""Build a manual listening report from measured streams, without synthesis."""
from pathlib import Path
import argparse
from array import array
import html
import json
import math
import shutil
import sys
import wave

ROOT=Path(__file__).resolve().parents[2]
LABELS={'natural':'Исходный','restrained':'Сдержанный','scott':'Scott','digital':'Цифровой'}


def metrics(path):
    with wave.open(str(path),'rb') as source:
        assert (source.getnchannels(),source.getsampwidth(),source.getframerate())==(1,2,24000)
        samples=array('h',source.readframes(source.getnframes()))
    if sys.byteorder!='little': samples.byteswap()
    assert samples
    return dict(seconds=len(samples)/24000,peak=max(abs(v) for v in samples)/32768,
        rms=math.sqrt(sum(v*v for v in samples)/len(samples))/32768,
        at_limit_fraction=sum(abs(v)>=31129 for v in samples)/len(samples))


def schedule(row):
    start=row['blocks'][0]['arrival_seconds']
    end=0.;gaps=[];segments=[]
    for block in row['blocks']:
        ready=block['arrival_seconds']-start
        gap=max(0.,ready-end)
        if gap: gaps.append(gap)
        begin=max(end,ready);end=begin+block['seconds']
        segments.append((begin,end))
    return dict(total_seconds=end,gap_seconds=sum(gaps),max_gap_seconds=max(gaps,default=0.),segments=segments)


def player(label,path):
    return f'<div class="player"><h3>{html.escape(label)}</h3><audio controls preload="none" src="{html.escape(path,quote=True)}"></audio></div>'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'reports/voice-streaming')
    args=parser.parse_args();folder=args.output
    reports=[('',json.loads((folder/'streaming.json').read_text(encoding='utf-8')))]
    extra=folder/'fresh-profiles/streaming.json'
    if extra.is_file(): reports.append(('fresh-profiles/',json.loads(extra.read_text(encoding='utf-8'))))
    rows=[];cards=[];stats=[]
    for prefix,report in reports:
        assert report['protected_files_unchanged'] and not report['health']['errors']
        for row in report['results']:
            timing=schedule(row);audio=metrics(folder/prefix/row['joined'])
            assert abs(audio['seconds']-row['audio_seconds'])<.002
            timed=metrics(folder/prefix/row['timed'])
            assert abs(timed['seconds']-timing['total_seconds'])<.004
            stats.append(dict(case=row['id'],profile=row['profile'],source=prefix or './',
                first_seconds=row['first_audio_seconds'],total_seconds=row['total_seconds'],
                audio=audio,schedule=timing))
            recognition=row.get('recognition',{})
            wer=max(v['word_error_rate'] for v in recognition.values()) if recognition else None
            state='Новый синтез' if prefix or row['profile']=='natural' else 'Обработка готового WAV'
            rows.append(f'<tr><td>{html.escape(row["title"])} · {LABELS[row["profile"]]}<small>{state}</small></td>'
                f'<td>{row["first_audio_seconds"]:.2f} с</td><td>{row["total_seconds"]:.2f} с</td>'
                f'<td>{audio["seconds"]:.2f} с</td><td>{timing["gap_seconds"]:.2f} с</td><td>{wer:.1%}</td></tr>')
            segments=''.join(f'<i style="left:{100*a/timing["total_seconds"]:.3f}%;width:{100*(b-a)/timing["total_seconds"]:.3f}%"></i>'
                for a,b in timing['segments'])
            cards.append(f'<section><div class="eyebrow">{state} · {LABELS[row["profile"]]}</div><h2>{html.escape(row["title"])}</h2>'
                f'<p>{html.escape(row["text"])}</p><div class="timeline" role="img" aria-label="Звук и паузы: зелёные блоки — речь">{segments}</div>'
                f'<p class="caption">После первого звука: {timing["total_seconds"]:.2f} с вместе с ожиданием следующих блоков. '
                f'Самая длинная пауза — {timing["max_gap_seconds"]:.2f} с.</p><div class="grid">'
                +player('Поток с измеренными паузами',prefix+row['timed'])
                +player('Полный WAV',prefix+row['complete'])+'</div><details><summary>Поток без ожидания блоков</summary>'
                +player('Для сравнения стыков и тембра',prefix+row['joined'])
                +f'<p>Пик: {audio["peak"]:.3f}; RMS: {audio["rms"]:.3f}; доля отсчётов у ограничителя ±0,95: '
                f'{audio["at_limit_fraction"]:.3%}. Контрольная сумма полного WAV: <code>{row["complete_sha256"]}</code>.</p></details></section>')
    main_report=reports[0][1];cold=main_report['results'][0]
    recognized=sum(len(row.get('recognition',{})) for _,report in reports for row in report['results'])
    errors=sum(v['word_error_rate']>0 for _,report in reports for row in report['results'] for v in row.get('recognition',{}).values())
    health_requests=sum(report['health']['requests'] for _,report in reports)
    max_health=max(report['health']['max_seconds'] for _,report in reports)
    cancel=max(report['cancel']['seconds'] for _,report in reports)
    controls=folder/'settings';controls.mkdir(exist_ok=True)
    images=[]
    for name in ('classic','glass-preparing','terminal-compact'):
        source=ROOT/f'ScottAI_qt/build/screenshots/voice/{name}.png'
        if source.is_file():
            shutil.copyfile(source,controls/(name+'.png'))
            images.append(f'<img loading="lazy" src="settings/{name}.png" alt="Настройки голоса: {name}">')
    document='''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Scott Voice — потоковый синтез</title><style>
*{box-sizing:border-box}body{margin:0;background:#10141b;color:#eef2f8;font:16px/1.55 system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:40px 24px}
h1{font-size:36px;line-height:1.15}h2{font-size:22px;margin:6px 0}h3{font-size:15px;margin:8px 0}p,small,.caption{color:#b9c5d6}small{display:block;font-size:12px}
.eyebrow{color:#73ceb5;font-size:13px}.lead{font-size:20px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}section{background:#19202b;border:1px solid #303d50;border-radius:16px;padding:22px;margin:20px 0}
audio{width:100%}.note{border-left:3px solid #73ceb5;padding-left:16px}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;min-width:720px}th,td{text-align:left;padding:14px 10px;border-bottom:1px solid #303d50}th{color:#73ceb5;font-size:13px}td{vertical-align:top}
.timeline{position:relative;height:18px;background:#35404f;border-radius:5px;overflow:hidden}.timeline i{position:absolute;height:100%;background:#73ceb5}details{margin-top:16px}summary{cursor:pointer;color:#73ceb5}code{overflow-wrap:anywhere;font-size:12px}img{width:100%;border-radius:12px;margin:12px 0}
@media(max-width:700px){.grid{grid-template-columns:1fr}main{padding:24px 16px}h1{font-size:28px}}
</style><main><div class="eyebrow">SCOTT VOICE · 7 ОКТЯБРЯ 2026 · RTX 3060</div><h1>Звук по мере синтеза</h1>'''
    document+=f'<p class="lead">Первый блок короткой фразы готов через {cold["first_audio_seconds"]:.2f} с после холодного запуска; '
    document+=f'полный WAV — через {cold["total_seconds"]:.2f} с.</p><p class="note">Режим «Раннее начало речи» в Настройки → Голос экспериментальный и по умолчанию выключен. '
    document+='Модель ещё создаёт звук медленнее речи, поэтому между блоками возможны паузы.</p>'
    document+='<p>Зелёные участки показывают звук, серые — ожидание. Запись с измеренными паузами моделирует поступление блоков, начиная с первого; '
    document+='начальная задержка указана отдельно. Это расчёт по времени выдачи WAV, без измерения звукового устройства. Запуск аудио — только вручную.</p>'
    document+='<div class="scroll"><table><thead><tr><th>Запись</th><th>Первый блок</th><th>Весь синтез</th><th>Речь</th><th>Паузы потока</th><th>WER</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'
    document+=f'<p>Whisper: {recognized-errors}/{recognized} WAV без ошибок слов; API здоровья: {health_requests} запросов без ошибок, максимум {max_health*1000:.1f} мс. '
    document+=f'Отмена дерева синтеза: до {cancel:.3f} с. Попадание в кеш: {main_report["cache"]["milliseconds"]:.2f} мс.</p>'
    document+='<p>Принятый эталон, голосовые настройки, модель, BF16/SDPA, 4 CPU-потока и выключенный RMSNorm сохранены. '
    document+='Полные исходные WAV совпали с принятыми образцами по SHA256. Промежуточное декодирование и постоянная громкость потока могут менять отсчёты; '
    document+='тембр и ударения нужно оценивать на слух.</p>'+''.join(cards)
    document+='<section><h2>Настройка в Qt</h2><p>Проверочные снимки трёх стилей с включённым переключателем. Рабочий выбор голоса и переключатель пользователя сохранены.</p>'+''.join(images)+'</section>'
    document+='<p>Исходные измерения: <a href="streaming.json">основной прогон</a> · <a href="fresh-profiles/streaming.json">новые цифровые профили</a>. '
    document+='Микрофон, проигрывание и команды в автоматической проверке не запускались.</p></main></html>'
    (folder/'index.html').write_text(document,encoding='utf-8')
    (folder/'metrics.json').write_text(json.dumps(dict(results=stats,recognized=recognized,word_errors=errors,
        health_requests=health_requests,health_max_seconds=max_health,cancel_max_seconds=cancel),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(samples=recognized,word_errors=errors,health_requests=health_requests,
        cancel_max_seconds=cancel,source_reports=len(reports))))


if __name__=='__main__': main()
