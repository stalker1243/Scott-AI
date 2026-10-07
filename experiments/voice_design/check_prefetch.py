"""Replay recorded phrases through the real voice adapter with a fake device."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import argparse
import hashlib
import html
import json
import shutil
import sys
import tempfile

import numpy as np

from check_streaming import protected
from check_output_stream import CapturedDevice
from build_buffer_preview import read_pcm
from trial_utils import ROOT,save_json
from speech_buffer import SpeechBuffer,BUFFER_MODES
from echo_reference import EchoReference
import speech_player
import scott_voice_engine
import voice_config
import audio_settings

# The adapter is exercised without constructing its legacy TTS engines.
with patch.dict(sys.modules,{'silero_tts':SimpleNamespace(is_available=lambda:False)}):
    import scott_voice


def groups(row,mode):
    buffer = SpeechBuffer(mode)
    released = []
    for block in row['blocks']:
        ready = buffer.push(SimpleNamespace(seconds=block['seconds']),block['last'])
        if ready:
            released.append(dict(ready=block['arrival_seconds'],seconds=sum(v.seconds for v in ready)))
    return released


def schedule(rows,mode,prefetch):
    """Calculated timeline: recorded model times, instantaneous device setup."""
    model_end,play_end = 0.,0.
    phrase_ends,model_starts,segments,boundaries = [],[],[],[]
    for i,row in enumerate(rows):
        if prefetch:
            start = max(model_end,phrase_ends[i-2] if i>=2 else 0.)
        else:
            start = max(model_end,play_end)
        model_starts.append(start)
        begin = None
        for group in groups(row,mode):
            due = start+group['ready']
            at = max(play_end,due)
            if begin is None:
                begin = at
            segments.append([at,at+group['seconds'],i])
            play_end = at+group['seconds']
        if i:
            boundaries.append(begin-phrase_ends[-1])
        phrase_ends.append(play_end)
        model_end = start+row['total_seconds']
    first = segments[0][0]
    speech = sum(b-a for a,b,_ in segments)
    return dict(first_seconds=first,end_seconds=play_end,after_start_seconds=play_end-first,
        gap_seconds=play_end-first-speech,boundary_gap_seconds=sum(boundaries),
        model_starts=model_starts,phrase_ends=phrase_ends,segments=segments)


def replay(rows,base,mode,prefetch,folder):
    device,reference = CapturedDevice(),EchoReference()
    player = speech_player.SpeechPlayer()
    calls = []
    voice = scott_voice.ScottVoice.__new__(scott_voice.ScottVoice)
    with tempfile.TemporaryDirectory(prefix='.prefetch-check-',dir=folder) as temporary:
        cache = Path(temporary)
        class RecordedEngine:
            generation = 0
            def stream(self,text,profile,on_audio,on_abort,generation):
                assert generation==0 and profile=='natural'
                row = next(v for v in rows if v['text']==text)
                calls.append(row['id'])
                created = []
                try:
                    for i,block in enumerate(row['blocks']):
                        source = base/f'{row["run"]}-{row["mode"]}'/f'{row["id"]}-block-{i:02}.wav'
                        path = cache/f'{row["id"]}-{i}.wav'
                        shutil.copyfile(source,path)
                        created.append(path)
                        on_audio(SimpleNamespace(path=str(path),seconds=block['seconds'],cached=False),block['last'])
                    return str(base/row['joined'])
                except Exception:
                    on_abort()
                    raise
                finally:
                    for path in created:
                        path.unlink(missing_ok=True)
        engine = RecordedEngine()
        with patch.object(speech_player,'sd',device), \
             patch.object(speech_player,'PLAYBACK_AVAILABLE',True), \
             patch.object(speech_player,'_muted',lambda:False), \
             patch.object(speech_player,'_volume',lambda:1.), \
             patch.object(speech_player,'_output_device',lambda:None), \
             patch.object(speech_player,'get_player',lambda:player), \
             patch.object(speech_player.SpeechPlayer,'_echo_reference',staticmethod(lambda:reference)), \
             patch.object(scott_voice_engine,'get_engine',lambda:engine), \
             patch.object(voice_config,'get_scott_buffer',lambda:mode), \
             patch.object(voice_config,'get_scott_profile',lambda:'natural'), \
             patch.object(audio_settings,'is_quiet',lambda:False):
            try:
                if prefetch:
                    assert voice.speak_stream_parts([v['text'] for v in rows])
                else:
                    for row in rows:
                        assert voice.speak_stream(row['text'])
                assert calls==[v['id'] for v in rows]
                assert not player.busy and not reference.playing
                assert not list(cache.glob('.scott-*'))
            finally:
                player.stop()
                if player._worker:
                    player._queue.put(None)
                    player._worker.join(3)
                    assert not player._worker.is_alive()
        assert not list(cache.iterdir())
    assert device.opened==device.closed
    recovered = np.rint(np.concatenate(device.pcm)*32768).astype('<i2').tobytes()
    expected = b''.join(read_pcm(base/row['joined']) for row in rows)
    assert recovered==expected
    return dict(pcm_equal=True,pcm_sha256=hashlib.sha256(recovered).hexdigest(),
        frames=len(recovered)//2,phrases=calls,native_opens=device.opened,
        native_closes=device.closed,legacy_opens=device.legacy_opened)


def build(source,folder):
    before = protected()
    validation = json.loads((source/'validation.json').read_text(encoding='utf-8'))
    report = dict(protected_sha256=before,results=[],source=str(source.relative_to(ROOT)),
        new_synthesis=False,new_stt=False,real_audio_device_opened=False,microphone_opened=False,
        queue_method='actual_adapter_and_queue_fake_device',
        timing_method='calculated_recorded_arrivals_no_device_latency')
    for comparison,base in [('ABBA',source),('BA',source/'reverse')]:
        speed = json.loads((base/'speed.json').read_text(encoding='utf-8'))
        runs = list(dict.fromkeys((r['run'],r['mode']) for r in speed['results']))
        for run,engine in runs:
            rows = [r for r in speed['results'] if (r['run'],r['mode'])==(run,engine)]
            sources = []
            for row in rows:
                checked = next(v for v in validation['results'] if v['comparison']==comparison and
                    (v['run'],v['case'],v['mode'])==(run,row['id'],engine))['recognition']['joined']
                assert checked['success'] and checked['word_error_rate']==0
                assert hashlib.sha256((base/row['joined']).read_bytes()).hexdigest()==checked['sha256']
                assert read_pcm(base/row['joined'])==b''.join(read_pcm(base/f'{run}-{engine}'/f'{row["id"]}-block-{i:02}.wav')
                    for i in range(len(row['blocks'])))
                sources.append(dict(case=row['id'],path=str((base/row['joined']).relative_to(ROOT)),
                    wav_sha256=checked['sha256'],source_wer=checked['word_error_rate']))
            assert [r['id'] for r in rows]==['status','technical','numbers']
            for mode in BUFFER_MODES:
                old_pcm = replay(rows,base,mode,False,folder)
                new_pcm = replay(rows,base,mode,True,folder)
                assert old_pcm['pcm_sha256']==new_pcm['pcm_sha256']
                old,new = schedule(rows,mode,False),schedule(rows,mode,True)
                assert abs(old['first_seconds']-new['first_seconds'])<1e-8
                assert new['end_seconds']<=old['end_seconds']+.001
                report['results'].append(dict(comparison=comparison,run=run,engine=engine,buffer=mode,
                    sources=sources,old=old,new=new,old_queue=old_pcm,new_queue=new_pcm,
                    calculated_end_saving_seconds=old['end_seconds']-new['end_seconds']))
    report['protected_files_unchanged'] = before==protected()
    assert report['protected_files_unchanged'] and len(report['results'])==24
    assert 'torch' not in sys.modules and not list(folder.glob('.prefetch-check-*'))
    report['summary'] = dict(verified_replies=24,verified_phrase_playbacks=144,
        all_pcm_equal=True,hardware_timing_measured=False,actual_model_speed_measured=False)
    return report


def timeline(value):
    first,end = value['first_seconds'],value['end_seconds']
    bars = ''.join(f'<i class="phrase{phrase}" style="left:{100*(a-first)/(end-first):.4f}%;width:{100*(b-a)/(end-first):.4f}%"></i>'
        for a,b,phrase in value['segments'])
    return f'<div class="timeline" role="img" aria-label="Речь и ожидание">{bars}</div>'


def render(report,folder):
    rows,cards = [],[]
    latest = [r for r in report['results'] if r['comparison']=='BA']
    for row in latest:
        engine = 'Ускоренный' if row['engine']=='accelerated' else 'Обычный'
        rows.append(f'<tr><td>{engine}</td><td>{BUFFER_MODES[row["buffer"]][0]}</td>'
            f'<td>{row["old"]["first_seconds"]:.2f} с</td><td>{row["old"]["boundary_gap_seconds"]:.2f} → {row["new"]["boundary_gap_seconds"]:.2f} с</td>'
            f'<td>{row["old"]["end_seconds"]:.2f} → {row["new"]["end_seconds"]:.2f} с</td><td>{row["calculated_end_saving_seconds"]:.2f} с</td></tr>')
        if row['engine']=='accelerated' and row['buffer'] in ('immediate','complete'):
            old,new = row['old'],row['new']
            cards.append(f'<section><h2>{BUFFER_MODES[row["buffer"]][0]}</h2><p>Три тестовые фразы: короткая, техническая и числовая. Цвет меняется с каждой частью; серое — ожидание.</p>'
                f'<h3>Раньше</h3>{timeline(old)}<p>Начало следующей подготовки: {old["model_starts"][1]:.2f} с. Конец ответа: {old["end_seconds"]:.2f} с.</p>'
                f'<h3>С подготовкой следующей части</h3>{timeline(new)}<p>Начало следующей подготовки: {new["model_starts"][1]:.2f} с. Конец ответа: {new["end_seconds"]:.2f} с.</p></section>')
    document = f'''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Scott Voice — подготовка следующей части</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#10141b;color:#eef2f8;font:16px/1.6 system-ui,sans-serif}}main{{max-width:1100px;margin:auto;padding:40px 24px}}h1{{font-size:34px;line-height:1.2}}h2{{font-size:23px}}h3{{font-size:16px}}a{{color:#73ceb5}}p{{color:#bdc9d8}}section{{background:#1b2330;border:1px solid #344153;border-radius:14px;padding:24px;margin:24px 0}}.note{{border-left:3px solid #73ceb5;padding-left:16px}}.timeline{{position:relative;height:20px;background:#354151;overflow:hidden;border-radius:4px}}.timeline i{{position:absolute;height:100%}}.phrase0{{background:#73ceb5}}.phrase1{{background:#77aee9}}.phrase2{{background:#ca9df0}}.scroll{{overflow:auto}}table{{width:100%;border-collapse:collapse;min-width:860px}}td,th{{padding:12px 8px;text-align:left;border-bottom:1px solid #344153}}th{{color:#73ceb5}}@media(max-width:700px){{main{{padding:24px 16px}}h1{{font-size:28px}}}}
</style><main><h1>Следующая часть готовится во время речи</h1>
<p>Ранний режим теперь освобождает синтезатор после подготовки фразы. Очередь продолжает её озвучивать, пока начинается следующий запрос. Одновременно допускаются текущая и одна следующая часть.</p>
<p class="note">Это расчёт на ранее записанных временах выдачи звука и проверка рабочей очереди с имитацией устройства. Нового синтеза и физического проигрывания не было. Нагрузка от копирования, аудиодрайвер и возможные изменения скорости Qwen не включены в расчёт.</p>
<p>24 варианта ответа из трёх тестовых фраз, 144 проигрывания через прежний и новый пути: PCM совпадает побайтово. Начальная задержка в расчёте сохраняется; уменьшается ожидание между частями. Если синтез слишком медленный, паузы остаются.</p>
{''.join(cards)}<h2>Последняя пара BA — расчёт</h2><div class="scroll"><table><thead><tr><th>Синтез</th><th>Запас</th><th>Первый звук</th><th>Ожидание между частями</th><th>Конец от запроса</th><th>Раньше на</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<section><h2>Отмена и файлы</h2><p>Смена ответа и тихий режим отменяют текущий звук и подготовленное продолжение. После частичной озвучки полного повтора нет. Блоки копируются во временную папку; каждый файл освобождается после окончания задания очереди, а папка — после освобождения всех блоков. Поэтому удаление исходных блоков работником не мешает следующей подготовке.</p></section>
<p><a href="prefetch.json">Данные, расчёт и SHA256</a> · <a href="../voice-prefetch-final-tests.log">Выбранные тесты</a> · <a href="../voice-prefetch-full-tests.log">Полная проверка backend</a> · <a href="../voice-buffering/index.html">Запас звука и прослушивание</a></p></main></html>'''
    (folder/'index.html').write_text(document,encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'reports/voice-stream-speed')
    parser.add_argument('--output',type=Path,default=ROOT/'reports/voice-prefetch')
    args = parser.parse_args()
    if (args.output/'prefetch.json').exists():
        raise ValueError('Choose a new report directory')
    args.output.mkdir(parents=True,exist_ok=True)
    report = build(args.source,args.output)
    save_json(args.output/'prefetch.json',report)
    render(report,args.output)
    print(json.dumps(report['summary']),flush=True)
    for row in report['results']:
        if row['comparison']=='BA':
            print(json.dumps(dict(engine=row['engine'],buffer=row['buffer'],
                old_end=row['old']['end_seconds'],new_end=row['new']['end_seconds'],
                old_boundary=row['old']['boundary_gap_seconds'],new_boundary=row['new']['boundary_gap_seconds'])),flush=True)


if __name__=='__main__':
    main()
