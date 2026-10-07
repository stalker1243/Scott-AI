"""Replay measured speech arrivals through the actual buffer without synthesis."""
from pathlib import Path
from types import SimpleNamespace
import argparse
import hashlib
import html
import json
import shutil
import sys
import tempfile
import threading
import time
import wave

from check_streaming import protected
from trial_utils import ROOT, save_json
from benchmark_base import Backend
from scott_voice_process import checksum
from speech_buffer import SpeechBuffer, BUFFER_MODES, join_wavs


def read_pcm(path):
    with wave.open(str(path), 'rb') as source:
        assert (source.getnchannels(), source.getsampwidth(), source.getframerate()) == (1, 2, 24000)
        data = source.readframes(source.getnframes())
        assert len(data) == source.getnframes() * 2
        return data


def schedule(groups):
    first = groups[0]['ready_seconds']
    end = first
    gaps, segments = [], []
    for group in groups:
        ready = group['ready_seconds']
        gap = max(0., ready-end)
        if gap:
            gaps.append(gap)
        begin = max(end, ready)
        end = begin + group['seconds']
        segments.append([begin-first, end-first])
    return dict(first_seconds=first, end_seconds=end, gap_seconds=sum(gaps),
        max_gap_seconds=max(gaps, default=0.), after_start_seconds=end-first, segments=segments)


def timed_audio(groups, blocks, destination):
    first = groups[0]['ready_seconds']
    frame_count = 0
    reconstructed = bytearray()
    merge_times = []
    with tempfile.TemporaryDirectory(prefix='.buffer-build-', dir=destination.parent) as directory:
        with wave.open(str(destination), 'wb') as output:
            output.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            for index, group in enumerate(groups):
                paths = [blocks[i].path for i in group['indices']]
                if len(paths) > 1:
                    begin = time.perf_counter()
                    joined = join_wavs(paths, Path(directory)/f'{index}.wav')
                    merge_times.append(time.perf_counter()-begin)
                    data = read_pcm(joined)
                else:
                    data = read_pcm(paths[0])
                due = round((group['ready_seconds']-first)*24000)
                silence = max(0, due-frame_count)
                output.writeframesraw(b'\0\0'*silence)
                output.writeframesraw(data)
                frame_count += silence + len(data)//2
                reconstructed.extend(data)
    return bytes(reconstructed), max(merge_times, default=0.)


def build(source, folder):
    validation = json.loads((source/'validation.json').read_text(encoding='utf-8'))
    before = protected()
    report = dict(protected_sha256=before, results=[], samples=[], source=str(source.relative_to(ROOT)))
    for comparison, base in [('ABBA', source), ('BA', source/'reverse')]:
        recorded = json.loads((base/'speed.json').read_text(encoding='utf-8'))
        for row in recorded['results']:
            recognized = next(v for v in validation['results'] if v['comparison']==comparison and
                v['run']==row['run'] and v['case']==row['id'] and v['mode']==row['mode'])['recognition']['joined']
            joined = base/row['joined']
            assert recognized['success'] and recognized['word_error_rate']==0 and checksum(joined)==recognized['sha256']
            name = f'{row["run"]}-{row["mode"]}'
            blocks = [SimpleNamespace(path=str(base/name/f'{row["id"]}-block-{i:02}.wav'),
                seconds=block['seconds'], index=i) for i, block in enumerate(row['blocks'])]
            expected = read_pcm(joined)
            assert b''.join(read_pcm(block.path) for block in blocks)==expected
            for block in blocks:
                assert abs(len(read_pcm(block.path))/48000-block.seconds)<.002
            for mode in BUFFER_MODES:
                buffer = SpeechBuffer(mode)
                groups = []
                for block, arrival in zip(blocks, row['blocks']):
                    ready = buffer.push(block, arrival['last'])
                    if ready:
                        groups.append(dict(ready_seconds=arrival['arrival_seconds'], seconds=sum(v.seconds for v in ready),
                            indices=[v.index for v in ready]))
                assert [i for group in groups for i in group['indices']]==list(range(len(blocks)))
                timing = schedule(groups)
                if mode=='immediate':
                    assert abs(timing['gap_seconds']-row['schedule']['gap_seconds'])<.003
                result = dict(comparison=comparison, run=row['run'], engine=row['mode'], case=row['id'],
                    title=row['title'], buffer=mode, audio_seconds=row['audio_seconds'], schedule=timing,
                    original_pcm_sha256=hashlib.sha256(expected).hexdigest(), pcm_equal=True)
                report['results'].append(result)
                if comparison=='BA' and row['mode']=='accelerated' and row['id'] in ('technical', 'numbers'):
                    destination = folder/f'{row["id"]}-{mode}.wav'
                    data, merge_time = timed_audio(groups, blocks, destination)
                    assert data==expected
                    result = dict(**result, path=destination.name, text=row['text'], sha256=checksum(destination),
                        merge_seconds=merge_time, source_joined_sha256=recognized['sha256'])
                    assert abs(len(read_pcm(destination))/48000-timing['after_start_seconds'])<.004
                    report['samples'].append(result)
    report['protected_files_unchanged'] = before==protected()
    assert report['protected_files_unchanged'] and len(report['results'])==72 and len(report['samples'])==8
    assert 'torch' not in sys.modules
    return report


def recognize(report, folder):
    backend = Backend('http://127.0.0.1:8000')
    backend.get('/health')
    stop = threading.Event()
    health, errors = [], []
    def monitor():
        while not stop.is_set():
            try:
                _, elapsed = backend.get('/health', timeout=3)
                health.append(elapsed)
            except Exception as error:
                errors.append(type(error).__name__)
            stop.wait(.15)
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    known = {}
    try:
        for row in report['samples']:
            path = folder/row['path']
            assert checksum(path)==row['sha256']
            if row['sha256'] not in known:
                known[row['sha256']] = backend.transcribe(path, row['text'])
            row['recognition'] = known[row['sha256']]
            save_json(folder/'buffering.json', report)
            print(json.dumps(dict(case=row['case'], buffer=row['buffer'], wer=row['recognition']['word_error_rate'])), flush=True)
    finally:
        stop.set(); thread.join(5)
        report['health'] = dict(requests=len(health), errors=errors, max_seconds=max(health, default=0.))
        report['unique_stt_requests'] = len(known)
        save_json(folder/'buffering.json', report)
    assert not errors and all(v['recognition']['success'] for v in report['samples'])


def render(report, folder):
    rows, cards = [], []
    latest = [v for v in report['results'] if v['comparison']=='BA']
    for row in latest:
        timing = row['schedule']
        engine = 'Обычный' if row['engine']=='original' else 'Ускоренный'
        rows.append(f'<tr><td>{html.escape(row["title"])}<small>{engine}</small></td><td>{BUFFER_MODES[row["buffer"]][0]}</td>'
            f'<td>{timing["first_seconds"]:.2f} с</td><td>{timing["gap_seconds"]:.2f} с</td>'
            f'<td>{timing["max_gap_seconds"]:.2f} с</td><td>{timing["end_seconds"]:.2f} с</td></tr>')
    for case in ('technical', 'numbers'):
        samples = [v for v in report['samples'] if v['case']==case]
        options, variants = [], []
        for row in samples:
            timing = row['schedule']; mode = row['buffer']
            recognition = row.get('recognition')
            words = f'Whisper: {recognition["word_error_rate"]:.1%} ошибок слов.' if recognition else 'Whisper: ещё не проверено.'
            options.append(f'<option value="{mode}">{BUFFER_MODES[mode][0]}</option>')
            segments = ''.join(f'<i style="left:{100*a/timing["after_start_seconds"]:.3f}%;width:{100*(b-a)/timing["after_start_seconds"]:.3f}%"></i>'
                for a,b in timing['segments'])
            variants.append(f'<div data-mode="{mode}"'+(' hidden' if mode!='immediate' else '')+'>'
                f'<div class="stats"><span>Начало <b>{timing["first_seconds"]:.2f} с</b></span><span>Паузы <b>{timing["gap_seconds"]:.2f} с</b></span>'
                f'<span>Конец <b>{timing["end_seconds"]:.2f} с</b></span></div><div class="timeline" role="img" aria-label="Речь и ожидание блоков">{segments}</div>'
                f'<audio controls preload="none" src="{row["path"]}"></audio><p>{words}</p></div>')
        cards.append(f'<section><div class="eyebrow">Ускоренный синтез · последний BA</div><h2>{html.escape(samples[0]["title"])}</h2>'
            f'<p>{html.escape(samples[0]["text"])}</p><label>Запас звука <select aria-label="Запас звука">'+''.join(options)+'</select></label>'+''.join(variants)+'</section>')
    recognized = [v['recognition'] for v in report['samples'] if 'recognition' in v]
    complete = [v['recognition'] for v in report['samples'] if v['buffer']=='complete' and 'recognition' in v]
    accuracy_note = (f'В записях с паузами Whisper может ошибаться. «Вся фраза»: {sum(v["word_error_rate"]==0 for v in complete)}/{len(complete)} без ошибок слов.'
        if recognized else 'Влияние пауз на распознавание проверяется отдельно через локальный Whisper.')
    status = f'Whisper: проверено {len(recognized)}/{len(report["samples"])} записей; без ошибок слов — {sum(v["word_error_rate"]==0 for v in recognized)}.'
    if 'health' in report:
        status += f' Backend: {report["health"]["requests"]} health-запросов без ошибок; максимум {1000*report["health"]["max_seconds"]:.1f} мс.'
    images = []
    (folder/'settings').mkdir(exist_ok=True)
    for name in ('classic', 'glass-preparing', 'terminal-compact'):
        source = ROOT/f'ScottAI_qt/build/screenshots/voice/{name}.png'
        if source.is_file():
            shutil.copyfile(source, folder/'settings'/f'{name}.png')
            images.append(f'<img loading="lazy" src="settings/{name}.png" alt="Запас звука в настройках: {name}">')
    document = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Scott Voice — запас звука</title><style>
*{box-sizing:border-box}body{margin:0;background:#10141b;color:#eef2f8;font:16px/1.6 system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:40px 24px}h1{font-size:36px;line-height:1.2}h2{font-size:22px}p,small{color:#bac6d6}small{display:block}.eyebrow,a{color:#73ceb5}.lead{font-size:20px}.note{border-left:3px solid #73ceb5;padding-left:16px}section{background:#19202b;border:1px solid #303d50;border-radius:16px;padding:24px;margin:24px 0}select{background:#10141b;color:#eef2f8;padding:10px 18px;border:1px solid #52647d;border-radius:8px;font:inherit;margin-left:12px}.stats{display:flex;gap:28px;flex-wrap:wrap;margin:22px 0 12px}.stats span{color:#bac6d6}.stats b{color:#eef2f8}.timeline{position:relative;height:18px;background:#35404f;border-radius:5px;overflow:hidden;margin-bottom:16px}.timeline i{position:absolute;height:100%;background:#73ceb5}audio,img{width:100%}img{border-radius:12px;margin:12px 0}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;min-width:760px}th,td{text-align:left;padding:12px 8px;border-bottom:1px solid #303d50}th{color:#73ceb5}summary{cursor:pointer;color:#73ceb5}@media(max-width:700px){main{padding:24px 16px}h1{font-size:28px}.stats{gap:14px}}
</style><main><div class="eyebrow">SCOTT VOICE · ЗАПАС ЗВУКА</div><h1>Меньше ожидания между блоками</h1>
<p class="lead">Выбор в Настройки → Голос → Раннее начало речи → Запас звука.</p>
<p class="note">Больше накопленного звука — позже начало, меньше пауз в середине. «Вся фраза» готовит её полностью перед воспроизведением. По умолчанию сохранён режим «Сразу».</p>
<p>Здесь повторены реальные времена прихода блоков из ABBA + BA; нового синтеза не было. Проверены 18 потоков в четырёх режимах. Буфер не ускоряет модель, PCM сохраняется побайтово. Время настройки устройства вывода не измерялось.</p>
<p>Зелёное — речь, серое — ожидание. Аудио начинается с первого звука; начальная задержка указана отдельно. Прослушивание запускается вручную.</p>'''
    document += f'<p>Исходная речь без ожидания блоков распознана без ошибок. {accuracy_note} Ноль ошибок распознавания не оценивает тембр и ударения.</p>'
    document += ''.join(cards)+f'<p>{status}</p><details><summary>Все варианты последних двух прогонов</summary><div class="scroll"><table><thead><tr>'
    document += '<th>Фраза</th><th>Запас</th><th>Начало</th><th>Сумма пауз</th><th>Макс. пауза</th><th>Конец от запроса</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div></details>'
    document += '<section><h2>Настройки Qt</h2><p>Три стиля; выбор отключён на время подготовки и без соединения.</p>'+''.join(images)+'</section>'
    document += '<p>Все 72 расчёта, SHA256 и распознавание: <a href="buffering.json">измерения</a>. Голос, настройки и эталон сохранены.</p></main>'
    document += '''<script>document.querySelectorAll('section select').forEach(select=>select.addEventListener('change',()=>{const section=select.closest('section');section.querySelectorAll('audio').forEach(audio=>audio.pause());section.querySelectorAll('[data-mode]').forEach(view=>view.hidden=view.dataset.mode!==select.value);}));document.querySelectorAll('audio').forEach(audio=>audio.addEventListener('play',()=>document.querySelectorAll('audio').forEach(other=>{if(other!==audio)other.pause();})));</script></html>'''
    (folder/'index.html').write_text(document, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT/'reports/voice-stream-speed')
    parser.add_argument('--output', type=Path, default=ROOT/'reports/voice-buffering')
    parser.add_argument('--render-only', action='store_true')
    parser.add_argument('--recognize', action='store_true')
    args = parser.parse_args()
    source, folder = args.source.resolve(), args.output.resolve()
    assert source.is_relative_to(ROOT) and folder.is_relative_to(ROOT/'reports') and folder!=source
    path = folder/'buffering.json'
    if args.render_only:
        report = json.loads(path.read_text(encoding='utf-8'))
    else:
        if path.exists(): raise ValueError('Choose a new output folder')
        folder.mkdir(parents=True, exist_ok=True)
        report = build(source, folder)
        save_json(path, report)
    if args.recognize:
        recognize(report, folder)
    assert report['protected_sha256']==protected()
    if all('recognition' in row for row in report['samples']):
        report['recognition_complete'] = True
        report['word_error_free_count'] = sum(row['recognition']['word_error_rate']==0 for row in report['samples'])
        assert all(row['recognition']['success'] for row in report['samples']) and not report['health']['errors']
        save_json(path, report)
    render(report, folder)
    print(json.dumps(dict(streams=len(report['results'])//4, schedules=len(report['results']),
        samples=len(report['samples']), pcm_equal=all(v['pcm_equal'] for v in report['results']),
        merge_max_ms=round(1000*max(v['merge_seconds'] for v in report['samples']),3))))


if __name__=='__main__': main()
