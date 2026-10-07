"""Check recorded synthetic latency samples through local STT; no command execution."""
from pathlib import Path
import argparse
import html
import json
import threading
import wave

from benchmark_base import Backend
from trial_utils import ROOT, save_json
import sys
sys.path.insert(0, str(ROOT/'backend'))
from scott_voice_process import checksum


def protected_hashes():
    paths = ['.env', 'backend/data/voice_config.json', 'backend/data/audio_config.json',
             'reports/voice-design/reference/scott-reference.wav',
             'assets/scott-voice/reference/scott-reference.wav',
             'voice-runtime/reports/voice-design/reference/scott-reference.wav']
    return {name:checksum(ROOT/name) for name in paths if (ROOT/name).is_file()}


def check_samples(output, report):
    before = protected_hashes()
    # Joining already-generated WAVs is only for manual comparison in the report.
    # Real playback can have longer pauses while subsequent chunks are synthesized.
    with wave.open(str(output/'short-first-joined.wav'), 'wb') as combined:
        combined.setparams((1,2,24000,0,'NONE','not compressed'))
        for index, row in enumerate(report['variants']['short_first']['outputs']):
            with wave.open(str(output/row['audio']), 'rb') as source:
                assert (source.getnchannels(), source.getsampwidth(), source.getframerate()) == (1,2,24000)
                if index:
                    combined.writeframes(b'\0\0'*6000)
                combined.writeframes(source.readframes(source.getnframes()))
    backend = Backend('http://127.0.0.1:8000')
    health, errors = [], []
    stop = threading.Event()
    def monitor():
        while not stop.is_set():
            try:
                _, elapsed = backend.get('/health')
                health.append(elapsed)
            except Exception as error:
                errors.append(type(error).__name__)
            stop.wait(.1)
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    results = []
    try:
        for variant, entry in report['variants'].items():
            for row in entry['outputs']:
                assert checksum(output/row['audio']) == row['sha256']
                results.append(dict(variant=variant, audio=row['audio'],
                    recognition=backend.transcribe(output/row['audio'], row['text'])))
        results.append(dict(variant='joined', audio='short-first-joined.wav',
            recognition=backend.transcribe(output/'short-first-joined.wav', report['text'])))
    finally:
        stop.set(); thread.join(timeout=6)
    unchanged = before == protected_hashes()
    validation = dict(results=results, health_requests=len(health), health_errors=errors,
        health_max_seconds=round(max(health),4) if health else None,
        protected_files_unchanged=unchanged, protected_sha256=before)
    save_json(output/'validation.json', validation)
    return validation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/voice-latency')
    parser.add_argument('--render-only', action='store_true', help='Reuse saved STT results without backend access.')
    args = parser.parse_args()
    report = json.loads((args.output/'latency.json').read_text(encoding='utf-8'))
    validation = (json.loads((args.output/'validation.json').read_text(encoding='utf-8'))
                  if args.render_only else check_samples(args.output, report))
    results = validation['results']
    changed_results = [r for r in results if r['variant'] != 'original']
    assert validation['protected_files_unchanged']
    assert len(results) == 4 and all(r['recognition']['success'] for r in results)
    assert len(changed_results) == 3 and all(r['recognition']['word_error_rate']==0 for r in changed_results)
    assert validation['health_requests'] and not validation['health_errors']
    baseline_wer = next(r['recognition']['word_error_rate'] for r in results if r['variant']=='original')
    original, changed = report['variants']['original'], report['variants']['short_first']
    rows = ''.join(f'<li>{html.escape(row["text"])} <span>{row["synthesis_seconds"]:.1f} с подготовки</span>'
        f'<audio controls preload="none" src="{html.escape(row["audio"])}"></audio></li>' for row in changed['outputs'])
    document = f'''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Scott Voice — начало ответа</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#10141b;color:#eef2f8;font:16px/1.55 system-ui,sans-serif}}
main{{max-width:1000px;margin:auto;padding:48px 24px}}h1{{font-size:34px;line-height:1.15;margin:12px 0 20px}}
p{{color:#b9c5d6}}.eyebrow{{color:#73ceb5;font-size:13px;letter-spacing:2px}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
section{{background:#19202b;border:1px solid #303d50;border-radius:18px;padding:24px}}h2{{margin:0 0 8px;font-size:20px}}
.metric{{font-size:42px;font-weight:650}}audio{{width:100%;margin-top:14px}}li{{padding:12px 0}}span{{display:block;color:#b9c5d6;font-size:14px}}
.note{{border-left:3px solid #73ceb5;padding-left:16px}}@media(max-width:640px){{.grid{{grid-template-columns:1fr}}main{{padding:30px 18px}}}}
</style><main><div class="eyebrow">SCOTT VOICE · 7 ОКТЯБРЯ 2026</div><h1>Первый фрагмент раньше</h1>
<p>Первое длинное предложение разделено по границе фразы. Эталон, модель и настройки вычислений прежние.</p>
<div class="grid"><section><h2>До изменения</h2><div class="metric">{original['first_audio_seconds']:.1f} с</div>
<p>До готовности первого звука. Всё предложение — {len(original['chunks'][0])} знак.</p><audio controls preload="none" src="original-1.wav"></audio></section>
<section><h2>После изменения</h2><div class="metric">{changed['first_audio_seconds']:.1f} с</div>
<p>До готовности первого звука. Первая фраза — {len(changed['chunks'][0])} знаков.</p><audio controls preload="none" src="short-first-joined.wav"></audio></section></div>
<p class="note">Здесь готовые части соединены с паузой 0,25 с для сравнения голоса. В приложении паузы могут быть длиннее:
генерация пока медленнее речи. Этот этап уменьшает ожидание начала ответа.</p>
<section><h2>Отдельные части</h2><ol>{rows}</ol></section><p>Синтетический текст: {html.escape(report['text'])}</p>
<p>Холодный запуск каждого варианта: RTX 3060, CUDA, BF16, SDPA, 4 CPU-потока, RMSNorm выключен.
Суммарная подготовка: {original['total_synthesis_seconds']:.1f} → {changed['total_synthesis_seconds']:.1f} с.
Повторные части из кеша: {', '.join(str(ms) for ms in changed['cache_ms'])} мс.</p>
<p>Whisper: обе новые части и объединённый WAV — 3/3 без ошибок слов. Исходная длинная запись: WER {baseline_wer:.1%}.
Распознавание проверяет слова; тембр и ударения оцениваются на слух. Эталон совпал по SHA256.
Микрофон, озвучивание и исполнение команд выключены.</p>
</main></html>'''
    (args.output/'index.html').write_text(document,encoding='utf-8')
    print(json.dumps(dict(samples=len(results), new_samples_wer_zero=True, baseline_wer=baseline_wer,
        health_requests=validation['health_requests'], health_max_seconds=validation['health_max_seconds'],
        protected_files_unchanged=validation['protected_files_unchanged'])))


if __name__ == '__main__':
    main()
