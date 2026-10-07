"""Measure real output using saved synthetic speech; never open an input stream.

Device inventory is the default. --play is required to produce sound. No model,
backend server, commands, microphone, settings writes or system volume changes.
"""
from pathlib import Path
import argparse
import hashlib
import html
import json
import sys
import tempfile
import threading
import time
from unittest.mock import patch
import wave

import numpy as np
import sounddevice as sd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'backend'))
import speech_player
import echo_reference
from speech_pipeline import QueuedSpeech


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protected():
    names = ['.env', 'backend/data/voice_config.json', 'backend/data/audio_config.json',
        'reports/voice-design/reference/scott-reference.wav',
        'assets/scott-voice/reference/scott-reference.wav',
        'voice-runtime/reports/voice-design/reference/scott-reference.wav',
        'voice-runtime/experiments/voice_design/models/base/scott-model.json']
    return {name: checksum(ROOT/name) for name in names if (ROOT/name).is_file()}


class MeasuredOutput:
    """Delegate to PortAudio while recording API times and submitted PCM hashes."""
    def __init__(self, records, latency=None):
        self.records = records
        self.latency = latency
        self.writing = threading.Event()

    def OutputStream(self, **options):
        if self.latency is not None:
            options['latency'] = self.latency
        opened = time.monotonic()
        native = sd.OutputStream(**options)
        row = dict(open_at=opened, open_seconds=time.monotonic()-opened, device=int(native.device),
            driver_latency_seconds=float(native.latency), blocks=[], actions=[])
        self.records.append(row)
        owner = self
        pcm_hash = hashlib.sha256()

        class Stream:
            def action(self, name):
                begin = time.monotonic()
                try:
                    return getattr(native, name)()
                finally:
                    row['actions'].append(dict(name=name, seconds=time.monotonic()-begin))

            def start(self): return self.action('start')
            def stop(self): return self.action('stop')
            def abort(self): return self.action('abort')
            def close(self): return self.action('close')

            def write(self, data):
                record = dict(frames=len(data), sha256=hashlib.sha256(data.tobytes()).hexdigest(),
                    begin=time.monotonic(), write_available=int(native.write_available))
                row['blocks'].append(record)
                pcm_hash.update(data.tobytes())
                row['submitted_pcm_sha256'] = pcm_hash.hexdigest()
                owner.writing.set()
                try:
                    record['underflow'] = bool(native.write(data))
                    return record['underflow']
                except Exception as error:
                    record['error'] = type(error).__name__
                    raise
                finally:
                    record['seconds'] = time.monotonic()-record['begin']

        return Stream()

    @staticmethod
    def play(data, rate, **options): return sd.play(data, rate, **options)
    @staticmethod
    def wait(): return sd.wait()
    @staticmethod
    def stop(): return sd.stop()


def inventory(device):
    outputs = [dict(info, index=i) for i, info in enumerate(sd.query_devices())
        if info['max_output_channels'] > 0]
    info = dict(sd.query_devices(device, 'output'))
    api = sd.query_hostapis(info['hostapi'])['name']
    sd.check_output_settings(device=device, channels=1, samplerate=24000, dtype='float32')
    return dict(sounddevice=sd.__version__, selected=info, host_api=api,
        mono_24k_supported=True, outputs=outputs)


def read_pcm(path):
    with wave.open(str(path), 'rb') as audio:
        if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 24000):
            raise ValueError('Expected mono PCM16 at 24 kHz')
        return audio.readframes(audio.getnframes())


def write_pcm(path, pcm):
    with wave.open(str(path), 'wb') as audio:
        audio.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        audio.writeframes(pcm)


def replay(paths, mode, device, volume, latency):
    records = []
    output = MeasuredOutput(records, latency)
    ref = echo_reference.EchoReference()
    player = speech_player.SpeechPlayer()
    owners, receipts = [], []
    started = time.monotonic()
    report = dict(mode=mode, streams=records, starvation_injected=False)
    with patch.object(speech_player, 'sd', output), \
         patch.object(speech_player, '_muted', lambda: False), \
         patch.object(speech_player, '_volume', lambda: volume), \
         patch.object(speech_player, '_output_device', lambda: device), \
         patch.object(speech_player.SpeechPlayer, '_echo_reference', staticmethod(lambda: ref)):
        try:
            if mode == 'whole_file':
                # This follows the ordinary sd.play()/wait() path, without instrumentation.
                assert player.play_and_wait(str(paths[0].parent/'whole.wav'), timeout=15)
            else:
                phrase_count = 2 if mode == 'prefetch' else 1
                for _ in range(phrase_count):
                    owner = QueuedSpeech(player, player.generation)
                    owners.append(owner)
                    for i, path in enumerate(paths):
                        owner.submit([path], i == len(paths)-1, use_stream=True)
                        if mode == 'starvation' and i == 0 and len(paths)>1:
                            # Let the first write finish, then simulate a late model block.
                            assert output.writing.wait(3)
                            deadline = time.monotonic()+3
                            while player._queue.unfinished_tasks and time.monotonic() < deadline:
                                time.sleep(.01)
                            time.sleep(1.2)
                            report['starvation_injected'] = True
                    owner.seal()
                    receipts.append(owner.ticket)
                cancelled_at = None
                if mode in ('cancel', 'cancel_resume'):
                    assert output.writing.wait(3)
                    time.sleep(.2)
                    begin = time.monotonic()
                    cancelled_at = begin
                    player.stop()
                    report['cancel_call_seconds'] = time.monotonic()-begin
                    assert not receipts[-1].result(2)
                    if mode == 'cancel_resume':
                        replacement = QueuedSpeech(player, player.generation)
                        owners.append(replacement)
                        for i, path in enumerate(paths):
                            replacement.submit([path], i==len(paths)-1, use_stream=True)
                        replacement.seal()
                        receipts.append(replacement.ticket)
                        assert replacement.ticket.result(15)
                        report['resume_open_seconds'] = records[-1]['open_at']-begin
                else:
                    for ticket in receipts:
                        assert ticket.result(20)
            deadline = time.monotonic()+5
            while player._queue.unfinished_tasks and time.monotonic() < deadline:
                time.sleep(.005)
            assert player._queue.unfinished_tasks == 0
            assert not player.busy and not ref.playing
            assert all(o._directory is None for o in owners)
            assert all(r.released.is_set() for r in receipts)
            if cancelled_at is not None and mode == 'cancel':
                report['cancel_release_seconds'] = time.monotonic()-cancelled_at
            report['seconds'] = time.monotonic()-started
            report['stats'] = player.stream_stats
            report['owned_files_released'] = True
            for row in records:
                row['open_at'] -= started
                for block in row['blocks']:
                    block['begin'] -= started
            if mode not in ('cancel', 'whole_file'):
                expected = hashlib.sha256(b''.join((np.frombuffer(read_pcm(p), dtype='<i2')
                    .astype(np.float32)/32768*volume).tobytes() for p in paths)).hexdigest()
                compared = records[-1:] if mode == 'cancel_resume' else records
                assert all(row['submitted_pcm_sha256'] == expected for row in compared)
                report['submitted_pcm_equal'] = True
        finally:
            for owner in owners:
                owner.seal()
            player.stop()
            if player._worker:
                player._queue.put(None)
                player._worker.join(5)
                assert not player._worker.is_alive(), 'Output worker did not finish'
    assert all(sum(a['name']=='close' for a in r['actions']) == 1 for r in records)
    return report


def render(report, folder):
    rows = []
    labels = dict(continuous='Блоки без ожидания', starvation='Поздний следующий блок',
        prefetch='Две фразы в очереди', cancel='Отмена', cancel_resume='Новая речь после отмены',
        whole_file='Целый WAV')
    for row in report['results']:
        latencies = ', '.join(f'{s["driver_latency_seconds"]*1000:.0f}' for s in row['streams']) or '—'
        cancel = f'{row["cancel_call_seconds"]*1000:.1f}' if 'cancel_call_seconds' in row else '—'
        rows.append(f'<tr><td>{labels[row["mode"]]}</td><td>{row["seconds"]:.3f}</td>'
            f'<td>{row["stats"]["opened"]}</td><td>{latencies}</td>'
            f'<td>{row["stats"]["underflows"]}</td><td>{cancel}</td><td>Да</td></tr>')
    info = report['inventory']
    document = f'''<!doctype html><html lang="ru"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Scott Voice — аудиоустройство</title>
<style>body{{margin:0;background:#10141b;color:#eef2f8;font:16px/1.6 system-ui}}main{{max-width:1050px;margin:auto;padding:32px 24px}}p{{color:#bdc9d8}}a,th{{color:#73ceb5}}table{{border-collapse:collapse;width:100%;min-width:850px}}td,th{{padding:12px 8px;text-align:left;border-bottom:1px solid #344153}}.scroll{{overflow:auto}}</style>
<main><h1>Вывод на настоящее аудиоустройство</h1>
<p>{html.escape(info['selected']['name'])} · {html.escape(info['host_api'])} · mono, 24 кГц · громкость теста {report['volume']*100:.0f}%</p>
<p>Рабочая очередь проиграла сохранённую синтетическую речь. Синтезатор, backend, микрофон и команды не запускались. Проверены порядок PCM на входе драйвера, освобождение WAV, завершение потока и отмена. Пользовательские настройки и эталон сохранены.</p>
<div class="scroll"><table><thead><tr><th>Проверка</th><th>Полное время, с</th><th>Потоков</th><th>Оценка драйвера, мс</th><th>Недостаток данных</th><th>Вызов отмены, мс</th><th>WAV освобождены</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<p>«Недостаток данных» — флаг PortAudio при write. Нулевой флаг не гарантирует отсутствия пауз: MME не отметил даже специально созданное ожидание. Проверка позднего блока имеет смысл только при нескольких исходных блоках. Оценка драйвера и время вызовов не измеряют момент появления звука в наушниках. Щелчки, тембр и акустическое эхоподавление требуют оценки на слух.</p>
<p>Семантика параметров проверена по <a href="https://python-sounddevice.readthedocs.io/en/0.5.5/api/streams.html">документации sounddevice 0.5.5</a>. Подготовка следующей части: <a href="../voice-prefetch/index.html">предыдущий отчёт</a>.</p>
</main></html>'''
    (folder/'index.html').write_text(document, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--play', action='store_true')
    parser.add_argument('--device', type=int)
    parser.add_argument('--volume', type=float, default=.25)
    parser.add_argument('--latency', choices=['low', 'high'])
    parser.add_argument('--block-seconds', type=float, default=1.)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/voice-device')
    parser.add_argument('--modes', nargs='+', default=['whole_file', 'continuous', 'starvation', 'prefetch', 'cancel'],
        choices=['whole_file', 'continuous', 'starvation', 'prefetch', 'cancel', 'cancel_resume'])
    args = parser.parse_args()
    if not 0 < args.volume <= .5:
        parser.error('Diagnostic volume must be between 0 and 0.5')
    if not .05 <= args.block_seconds <= 5:
        parser.error('Block duration must be between 0.05 and 5 seconds')
    if args.device is None:
        import audio_settings
        args.device = audio_settings.get_output_device()
    info = inventory(args.device)
    if not args.play:
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return
    if (args.output/'device.json').exists():
        parser.error('Choose a new --output directory to preserve earlier measurements')
    args.output.mkdir(parents=True, exist_ok=True)
    source = ROOT/'reports/voice-stream-speed/reverse/2-original/status-joined.wav'
    validation = json.loads((ROOT/'reports/voice-stream-speed/validation.json').read_text(encoding='utf-8'))
    recognized = next(r for r in validation['results'] if r['comparison']=='BA' and
        r['run']==2 and r['case']=='status' and r['mode']=='original')['recognition']['joined']
    assert checksum(source) == recognized['sha256'] and recognized['word_error_rate'] == 0
    before = protected()
    pcm = read_pcm(source)
    report = dict(inventory=info, volume=args.volume, requested_latency=args.latency,
        block_seconds=args.block_seconds,
        source=str(source.relative_to(ROOT)), source_sha256=checksum(source),
        protected_sha256=before, microphone_opened=False, new_synthesis=False,
        real_audio_device_opened=True, acoustic_timing_measured=False, results=[])
    with tempfile.TemporaryDirectory(prefix='.device-check-', dir=args.output) as temporary:
        folder = Path(temporary)
        write_pcm(folder/'whole.wav', pcm)
        paths = []
        block_bytes = round(24000*args.block_seconds)*2
        for i, offset in enumerate(range(0, len(pcm), block_bytes)):
            path = folder/f'{i:02}.wav'
            write_pcm(path, pcm[offset:offset+block_bytes])
            paths.append(path)
        for mode in args.modes:
            result = replay(paths, mode, args.device, args.volume, args.latency)
            report['results'].append(result)
            print(json.dumps(dict(mode=mode, seconds=result['seconds'], stats=result['stats'],
                cancel=result.get('cancel_call_seconds'), released=result.get('cancel_release_seconds'),
                resumed=result.get('resume_open_seconds')), ensure_ascii=False), flush=True)
    report['protected_files_unchanged'] = before == protected()
    assert report['protected_files_unchanged'] and 'torch' not in sys.modules
    (args.output/'device.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    render(report, args.output)


if __name__ == '__main__':
    main()
