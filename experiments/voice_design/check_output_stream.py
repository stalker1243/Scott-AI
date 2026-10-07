"""Verify recorded PCM through the real queue with an entirely fake audio device."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import argparse
import hashlib
import html
import json
import sys
import tempfile

import numpy as np

from check_streaming import protected
from build_buffer_preview import read_pcm
from trial_utils import ROOT, save_json
from speech_buffer import SpeechBuffer, BUFFER_MODES, join_wavs
from echo_reference import EchoReference
import speech_player


class CapturedDevice:
    """In-memory sink. No PortAudio/device API is called."""
    def __init__(self):
        self.pcm = []
        self.opened = self.closed = self.drained = 0
        self.legacy_opened = 0

    def OutputStream(self, **options):
        assert options == dict(samplerate=24000, channels=1, dtype='float32', device=None)
        owner = self
        class Stream:
            def start(self):
                owner.opened += 1
            def write(self, data):
                owner.pcm.append(data.copy())
                return False
            def stop(self):
                owner.drained += 1
            def abort(self):
                pass
            def close(self):
                owner.closed += 1
        return Stream()

    def play(self, data, rate, **options):
        assert rate == 24000 and options == dict(device=None)
        self.legacy_opened += 1
        self.pcm.append(data.copy())

    def wait(self):
        pass

    def stop(self):
        pass


def replay(paths, continuous):
    device, reference = CapturedDevice(), EchoReference()
    # Replace the whole audio API and every settings accessor before starting
    # a worker. This cannot reach the real sounddevice device or user settings.
    with patch.object(speech_player, 'sd', device), \
         patch.object(speech_player, 'PLAYBACK_AVAILABLE', True), \
         patch.object(speech_player, '_muted', lambda: False), \
         patch.object(speech_player, '_volume', lambda: 1.), \
         patch.object(speech_player, '_output_device', lambda: None), \
         patch.object(speech_player.SpeechPlayer, '_echo_reference', staticmethod(lambda: reference)):
        player = speech_player.SpeechPlayer()
        token = object()
        try:
            for i, path in enumerate(paths):
                last = i == len(paths)-1
                if continuous and len(paths)>1:
                    assert player.play_stream(str(path), token, last=last, timeout=10)
                else:
                    assert (player.play_and_wait if last else player.play)(str(path))
            stats = player.stream_stats
            assert not player.busy and not reference.playing
        finally:
            player.stop()
            if player._worker:
                player._queue.put(None)
                player._worker.join(3)
                assert not player._worker.is_alive()
    assert device.opened == device.closed
    data = np.concatenate(device.pcm)
    # PCM16 / 32768 is exactly representable in float32 at volume 1.
    recovered = np.rint(data*32768).astype('<i2').tobytes()
    return dict(opens=device.opened+device.legacy_opened, native_opens=device.opened,
        native_closes=device.closed, final_drains=device.drained, stats=stats,
        frames=len(data), pcm_sha256=hashlib.sha256(recovered).hexdigest()), recovered


def build(source, folder):
    before = protected()
    validation = json.loads((source/'validation.json').read_text(encoding='utf-8'))
    report = dict(method='actual_queue_fake_device_no_timing', results=[],
        source=str(source.relative_to(ROOT)), protected_sha256=before,
        microphone_opened=False, real_audio_device_opened=False, new_synthesis=False)
    for comparison, base in [('ABBA',source), ('BA',source/'reverse')]:
        speed = json.loads((base/'speed.json').read_text(encoding='utf-8'))
        for row in speed['results']:
            recognition = next(v for v in validation['results'] if v['comparison']==comparison and
                v['run']==row['run'] and v['case']==row['id'] and v['mode']==row['mode'])['recognition']['joined']
            joined = base/row['joined']
            assert hashlib.sha256(joined.read_bytes()).hexdigest()==recognition['sha256']
            assert recognition['success'] and recognition['word_error_rate']==0
            expected = read_pcm(joined)
            name = f'{row["run"]}-{row["mode"]}'
            blocks = [SimpleNamespace(path=str(base/name/f'{row["id"]}-block-{i:02}.wav'),
                seconds=b['seconds']) for i,b in enumerate(row['blocks'])]
            assert b''.join(read_pcm(b.path) for b in blocks)==expected
            for mode in BUFFER_MODES:
                with tempfile.TemporaryDirectory(prefix='.output-check-',dir=folder) as temporary:
                    buffer, paths = SpeechBuffer(mode), []
                    for i, block in enumerate(blocks):
                        ready = buffer.push(block, row['blocks'][i]['last'])
                        if ready:
                            paths.append(join_wavs([b.path for b in ready],Path(temporary)/f'{i}.wav')
                                if len(ready)>1 else ready[0].path)
                    old, old_pcm = replay(paths, False)
                    new, new_pcm = replay(paths, True)
                assert old_pcm == new_pcm == expected
                assert old['opens']==len(paths) and new['opens']==1
                assert new['native_opens']==int(len(paths)>1)
                report['results'].append(dict(comparison=comparison,run=row['run'],case=row['id'],
                    title=row['title'],engine=row['mode'],buffer=mode,groups=len(paths),old=old,new=new,
                    pcm_equal=True,source_wer=recognition['word_error_rate'],
                    source_joined_sha256=recognition['sha256']))
    report['protected_files_unchanged'] = before == protected()
    assert report['protected_files_unchanged'] and len(report['results'])==72
    assert 'torch' not in sys.modules and not list(folder.glob('.output-check-*'))
    report['summary'] = dict(verified_variants=len(report['results']),
        old_device_opens=sum(r['old']['opens'] for r in report['results']),
        new_device_opens=sum(r['new']['opens'] for r in report['results']),
        verified_pcm_equal=all(r['pcm_equal'] for r in report['results']),
        hardware_timing_measured=False)
    return report


def render(report,folder):
    rows = []
    for row in report['results']:
        if row['comparison']!='BA':
            continue
        engine = 'Ускоренный' if row['engine']=='accelerated' else 'Обычный'
        route = 'Один PCM-поток' if row['new']['native_opens'] else 'Готовый WAV'
        rows.append(f'<tr><td>{html.escape(row["title"])}<small>{engine}</small></td>'
            f'<td>{BUFFER_MODES[row["buffer"]][0]}</td><td>{row["old"]["opens"]}</td>'
            f'<td>{row["new"]["opens"]}</td><td>{route}</td><td>Совпадает</td></tr>')
    summary = report['summary']
    document = f'''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Scott Voice — один поток звука</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#10141b;color:#eef2f8;font:16px/1.6 system-ui,sans-serif}}main{{max-width:1100px;margin:auto;padding:40px 24px}}h1{{font-size:34px;line-height:1.2}}p,small{{color:#bdc9d8}}small{{display:block}}a,.label{{color:#73ceb5}}.stats{{display:flex;gap:24px;flex-wrap:wrap;margin:30px 0}}.stats div{{background:#1b2330;border-radius:12px;padding:18px 24px}}.stats b{{display:block;font-size:28px}}.note{{border-left:3px solid #73ceb5;padding-left:16px}}.scroll{{overflow:auto}}table{{width:100%;border-collapse:collapse;min-width:820px}}td,th{{padding:12px 8px;text-align:left;border-bottom:1px solid #344153}}th{{color:#73ceb5}}details{{margin-top:24px}}summary{{cursor:pointer}}@media(max-width:700px){{main{{padding:24px 16px}}h1{{font-size:28px}}}}
</style><main><div class="label">SCOTT VOICE · ВЫВОД ЗВУКА</div><h1>Один поток на несколько блоков</h1>
<p>При раннем начале речи очередь держит выходной поток открытым до последнего блока. Повторная настройка аудиоустройства между блоками убрана. Готовая целая фраза и кеш воспроизводятся одним WAV.</p>
<div class="stats"><div><b>{summary['verified_variants']}</b>варианта проверено</div><div><b>{summary['old_device_opens']} → {summary['new_device_opens']}</b>открытий устройства в имитации</div><div><b>100%</b>PCM совпадает с источниками</div></div>
<p class="note">Испытана рабочая очередь с имитацией устройства. Колонки и микрофон не включались. Это проверка числа открытий, порядка и сохранности звука; реальная задержка драйвера, щелчки и акустическое эхо ещё не измерены.</p>
<p>Повторены 18 сохранённых потоков × четыре режима запаса. Синтеза не было; настройки, эталон и файлы модели сохранены. PCM после float32-вывода восстановлен в PCM16 и побайтово сравнен с исходными фразами, которые ранее прошли Whisper с WER 0.</p>
<p>Новая подача не ускоряет Qwen. Если модель выдаёт следующий блок поздно, ожидание остаётся. Выбор запаса и начальную задержку можно сравнить в <a href="../voice-buffering/index.html">отчёте буферизации</a>.</p>
<h2>Последние прогоны BA</h2><div class="scroll"><table><thead><tr><th>Фраза</th><th>Запас</th><th>Открытий раньше</th><th>Теперь</th><th>Подача</th><th>PCM</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<details><summary>Отмена и эхоподавление</summary><p>При отмене поток прерывается через abort(), старый хвост очереди отбрасывается. Последний блок ждёт drain перед удалением временных WAV. Повторная отмена сохраняет задачу закрытия устройства. Для эхоподавления передаются блоки со временем начала; опора учитывает границы и паузы, хранит недавний звук и начало для калибровки задержки. Привязка основана на времени записи в поток; точность на физическом устройстве требует отдельной проверки.</p></details>
<p><a href="output.json">Все измерения и SHA256</a> · <a href="../voice-output-tests.log">113 выбранных тестов</a> · <a href="../voice-output-full-tests.log">Полная проверка backend</a></p>
<p>Семантика write/stop/abort: <a href="https://python-sounddevice.readthedocs.io/en/0.5.5/api/streams.html">официальная документация sounddevice 0.5.5</a>.</p></main></html>'''
    (folder/'index.html').write_text(document,encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'reports/voice-stream-speed')
    parser.add_argument('--output',type=Path,default=ROOT/'reports/voice-output')
    args = parser.parse_args()
    if (args.output/'output.json').exists():
        raise ValueError('Choose a new report directory')
    args.output.mkdir(parents=True,exist_ok=True)
    report = build(args.source,args.output)
    save_json(args.output/'output.json',report)
    render(report,args.output)
    print(json.dumps(report['summary']),flush=True)


if __name__=='__main__':
    main()
