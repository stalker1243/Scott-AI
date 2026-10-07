"""Create an offline listening check for an experimental faster Base configuration."""
from pathlib import Path
import argparse
import html
import json
import os

from trial_utils import ROOT, cases


def esc(value):
    return html.escape(str(value), quote=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/voice-speed-rms')
    args = parser.parse_args()
    result = json.loads((args.output/'speed.json').read_text(encoding='utf-8'))
    base_folder = ROOT/'reports/voice-base'
    base = json.loads((base_folder/'base.json').read_text(encoding='utf-8'))
    originals = {row['id']:row for row in base['results']}
    status = next(row for row in cases() if row['id']=='status')
    winner = next(row for row in result['results'] if row['candidate']==result['winner'])
    rows = [dict(**status, **winner, synthesis_seconds=winner['median_seconds'])]+result['validation']
    original_trial = next((row for row in result['results'] if row['candidate']=='original'), None)
    cards = []
    for row in rows:
        original = originals[row['id']]
        original_path = base_folder/original['audio']
        original_seconds = original['synthesis_seconds']
        if row['id']=='status' and original_trial:
            original_path = args.output/original_trial['audio']
            original_seconds = original_trial['median_seconds']
        links = [os.path.relpath(original_path,args.output).replace('\\','/'),row['audio']]
        times = [original_seconds,row['synthesis_seconds']]
        durations = [original_trial['seconds'] if row['id']=='status' and original_trial else original['seconds'],row['seconds']]
        players = []
        for label, link, time, duration in zip(('Исходный синтез','Проба ускорения'),links,times,durations,strict=True):
            players.append(f'<section><h3>{label}</h3><audio controls preload="metadata" aria-label="{label}: {esc(row["title"])}" src="{esc(link)}"></audio><p class="metric">{duration:.2f} с речи · {time:.2f} с генерации</p></section>')
        recognition = row['recognition']
        cards.append(f'<article><h2>{esc(row["title"])}</h2><p>{esc(row["text"])}</p><div class="players">'+''.join(players)+f'</div><details><summary>Распознанный текст · ошибки слов {recognition["word_error_rate"]*100:.1f}%</summary><p>{esc(recognition["heard"])}</p></details></article>')
    page = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Scott · Проверка ускорения голоса</title><style>
    :root{font-family:Segoe UI,system-ui,sans-serif;color-scheme:dark;background:#10141c;color:#edf2f7}*{box-sizing:border-box}body{margin:0}main{max-width:960px;margin:auto;padding:48px 24px}h1{font-size:32px;font-weight:600}h2{font-size:21px;font-weight:600}h3{font-size:15px;color:#b5cfda;font-weight:500}p{color:#b8c6d4;line-height:1.7}article{background:#191f29;border:1px solid #303a49;border-radius:18px;padding:24px;margin-top:22px}.players{display:grid;grid-template-columns:1fr 1fr;gap:24px}audio{width:100%;height:44px}.metric,details{font-size:13px;color:#9db2c1}summary{cursor:pointer}a{color:#9dc9de;text-decoration:none}a:hover{text-decoration:underline}.note{font-size:14px;margin-top:28px}@media(max-width:620px){main{padding:26px 16px}.players{grid-template-columns:1fr;gap:12px}}
    </style><main><h1>Проверка ускорения голоса</h1><p>Изменение способа вычислений может повлиять на паузы и тембр. Сравни новые записи с подтверждённым голосом перед переносом настроек в приложение.</p>'''+''.join(cards)+'''<p class="note">Короткий ответ: медиана двух замеров после прогрева каждого варианта в одном процессе. Остальные исходные записи и их время взяты из предыдущей проверки Base. Новые ядра меняют запись и иногда её длину; скорость оценивается также относительно длительности речи. Эти пробы ещё не меняют рабочий голос приложения.</p><a href="../scott-voice/index.html">← Выбор характера Scott Voice</a></main><script>document.querySelectorAll('audio').forEach(player=>player.addEventListener('play',()=>document.querySelectorAll('audio').forEach(other=>{if(other!==player)other.pause()})));</script></html>'''
    target = args.output/'index.html'
    target.write_text(page,encoding='utf-8')
    print(str(target.resolve()))


if __name__ == '__main__':
    main()
