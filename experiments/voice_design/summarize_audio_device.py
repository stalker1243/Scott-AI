"""Verify saved hardware measurements and render their consolidated report."""
from pathlib import Path
import hashlib
import html
import json

import numpy as np
from check_audio_device import ROOT, protected, read_pcm


def main():
    folder = ROOT/'reports/voice-device'
    names = ['', 'low', 'cancel-before', 'cancel-after', 'final', 'gaps-after']
    reports = {name: json.loads((folder/name/'device.json').read_text(encoding='utf-8')) for name in names}
    first = reports['']
    reference = first['protected_sha256']
    assert protected() == reference
    source = ROOT/first['source']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == first['source_sha256']
    pcm = np.frombuffer(read_pcm(source), dtype='<i2').astype(np.float32)/32768
    checked, streams, records = 0, 0, []
    for name, report in reports.items():
        assert report['protected_sha256'] == reference and report['protected_files_unchanged']
        assert report['source_sha256'] == first['source_sha256']
        assert report['microphone_opened'] is False and report['new_synthesis'] is False
        assert report['real_audio_device_opened'] and not report['acoustic_timing_measured']
        volume = report['volume']
        for row in report['results']:
            # The early long-block invocation had a single whole WAV, so this
            # particular row cannot demonstrate a late second block. Retain it.
            if row['mode']=='starvation' and row['stats']['blocks'] <= 1:
                continue
            checked += 1
            assert row['owned_files_released']
            for i, stream in enumerate(row['streams']):
                streams += 1
                assert sum(a['name']=='close' for a in stream['actions']) == 1
                position = 0
                joined_hash = hashlib.sha256()
                for block in stream['blocks']:
                    frames = block['frames']
                    expected = (pcm[position:position+frames]*volume).tobytes()
                    assert len(expected) == frames*4
                    assert hashlib.sha256(expected).hexdigest() == block['sha256']
                    joined_hash.update(expected)
                    position += frames
                    if name in ('cancel-after', 'final', 'gaps-after'):
                        assert frames <= 2400
                if 'submitted_pcm_sha256' in stream:
                    assert stream['submitted_pcm_sha256'] == joined_hash.hexdigest()
                cancelled = row['mode']=='cancel' or row['mode']=='cancel_resume' and i==0
                if not cancelled:
                    assert position == len(pcm)
            records.append(dict(directory=name or '.', **row))
    before = reports['cancel-before']['results'][0]['cancel_release_seconds']
    cancellations = [r['cancel_release_seconds'] for r in reports['final']['results'] if r['mode']=='cancel']
    resume = next(r['resume_open_seconds'] for r in reports['final']['results'] if r['mode']=='cancel_resume')
    assert len(cancellations)==3 and max(cancellations)<before
    assert reports['gaps-after']['results'][0]['starvation_injected']
    assert not list(folder.rglob('.device-check-*')) and not list(folder.rglob('.scott-prefetch-*'))
    final = dict(protected_files_unchanged=True, valid_hardware_checks=checked,
        native_streams_closed=streams, submitted_pcm_verified=True,
        cancel_before_seconds=before, cancel_after_seconds=cancellations,
        resume_open_seconds=resume, microphone_opened=False, new_synthesis=False,
        acoustic_timing_measured=False, excluded_single_block_starvation_rows=1)
    (folder/'verification.json').write_text(json.dumps(final, indent=2), encoding='utf-8')
    api = first['inventory']['host_api']
    device = html.escape(first['inventory']['selected']['name'])
    after_ms = ' / '.join(f'{t*1000:.1f}' for t in cancellations)
    high_latency = next(s['driver_latency_seconds'] for r in first['results'] for s in r['streams'])
    low_latency = next(s['driver_latency_seconds'] for r in reports['low']['results'] for s in r['streams'])
    table = []
    labels = dict(continuous='Блоки без ожидания', starvation='Поздний блок',
        prefetch='Две фразы', cancel='Отмена', cancel_resume='Ответ после отмены', whole_file='Целый WAV')
    for row in records:
        paths = row['directory']
        label = 'До исправления' if paths in ('.', 'cancel-before') else (
            'Сравнение малого буфера' if paths=='low' else 'После исправления')
        release = f'{row["cancel_release_seconds"]*1000:.1f}' if 'cancel_release_seconds' in row else '—'
        table.append(f'<tr><td>{label}</td><td>{labels[row["mode"]]}</td><td>{row["seconds"]:.3f}</td>'
            f'<td>{release}</td><td>{row["stats"]["underflows"]}</td></tr>')
    document = f'''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Scott Voice — вывод и отмена</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#10141b;color:#eef2f8;font:16px/1.6 system-ui}}main{{max-width:1080px;margin:auto;padding:40px 24px}}h1{{font-size:34px;line-height:1.2}}p,small{{color:#bdc9d8}}a,.label,th{{color:#73ceb5}}.stats{{display:flex;gap:18px;flex-wrap:wrap;margin:28px 0}}.stats div{{background:#1b2330;border-radius:12px;padding:18px 22px}}.stats b{{display:block;font-size:28px}}.note{{border-left:3px solid #73ceb5;padding-left:16px}}.scroll{{overflow:auto}}table{{width:100%;border-collapse:collapse;min-width:780px}}td,th{{padding:12px 8px;text-align:left;border-bottom:1px solid #344153}}details{{margin:24px 0}}summary{{cursor:pointer}}audio{{width:min(100%,500px)}}@media(max-width:700px){{main{{padding:24px 16px}}h1{{font-size:28px}}}}
</style><main><div class="label">SCOTT VOICE · АУДИОУСТРОЙСТВО</div><h1>Быстрая отмена длинной записи</h1>
<p>Сохранённая синтетическая речь проиграна на настоящем устройстве: {device} · {html.escape(api)} · mono, 24 кГц. Громкость проверки — 25%.</p>
<div class="stats"><div><b>{before:.2f} с → ≈14 мс</b>освобождение очереди после отмены</div><div><b>{resume*1000:.0f} мс</b>до открытия нового потока</div><div><b>{checked}</b>проверок вывода</div></div>
<p>MME быстро принимал abort(), но длинный write() продолжал удерживать очередь. Теперь речь записывается порциями по 100 мс с проверкой отмены между ними. В трёх повторах освобождение заняло {after_ms} мс. Следующий ответ использовал ту же очередь и новый выходной поток.</p>
<p>Значения и порядок PCM сохранены на входе драйвера. Все {streams} проверенных выходных потоков закрыты, копии WAV освобождены. Голос, его эталон, модель, настройки приложения и звуковой драйвер сохранены.</p>
<p class="note">Это времена вызовов API и освобождения очереди. Момент появления звука в наушниках не записывался. Микрофон, backend, команды, Whisper и новый синтез не запускались. Звучание стыков и акустическое эхо ещё нужно оценить на слух.</p>
<h2>Реплика для прослушивания</h2><p>Исходный принятый тембр, без новой генерации или обработки:</p><audio controls preload="none" src="../voice-stream-speed/reverse/2-original/status-joined.wav"></audio>
<details><summary>Подробные замеры</summary><div class="scroll"><table><thead><tr><th>Режим</th><th>Проверка</th><th>Полное время, с</th><th>Освобождение после отмены, мс</th><th>Флаги underflow</th></tr></thead><tbody>{''.join(table)}</tbody></table></div>
<p>Нулевой underflow не гарантирует отсутствия пауз: MME не отметил даже намеренное ожидание позднего блока. Один прогон с целым WAV исключён из оценки позднего блока, поскольку второго блока в нём не было; исходная запись замера сохранена.</p>
<p>Оценка задержки потока от драйвера — {high_latency*1000:.0f} мс. Отдельное сравнение low уменьшило её до {low_latency*1000:.0f} мс; приложение сохраняет прежний буфер. Это оценка PortAudio, акустическое время не измерялось.</p></details>
<p><a href="verification.json">Проверка измерений и PCM</a> · <a href="final/device.json">Последние замеры</a> · <a href="../voice-prefetch/index.html">Подготовка следующей части</a> · <a href="https://python-sounddevice.readthedocs.io/en/0.5.5/api/streams.html">Документация sounddevice</a></p>
</main></html>'''
    (folder/'index.html').write_text(document, encoding='utf-8')
    print(json.dumps(final))


if __name__=='__main__':
    main()
