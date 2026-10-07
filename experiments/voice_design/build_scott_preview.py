"""Build the offline listening comparison for Scott Voice colourings."""
from pathlib import Path
import argparse
import html
import json
import os

from trial_utils import ROOT


def esc(value):
    return html.escape(str(value), quote=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/scott-voice')
    args = parser.parse_args()
    result = json.loads((args.output/'scott-voice.json').read_text(encoding='utf-8'))
    cards = []
    for case_id in dict.fromkeys(row['id'] for row in result['results']):
        rows = [row for row in result['results'] if row['id']==case_id]
        original = os.path.relpath(ROOT/rows[0]['source_audio'], args.output).replace('\\','/')
        players = f'<section class="player"><h3>Исходный голос</h3><p>Выбранный тембр «Чуть строгий».</p><audio controls preload="metadata" aria-label="Исходный голос: {esc(rows[0]["title"])}" src="{esc(original)}"></audio></section>'
        for profile, row in zip(result['profiles'], rows, strict=True):
            recognition = row.get('recognition')
            check = ''
            if recognition:
                check = f'<details><summary>Whisper · ошибки слов {recognition["word_error_rate"]*100:.1f}%</summary><p>{esc(recognition["heard"])}</p></details>'
            players += f'''<section class="player {'recommended' if profile['id']=='scott' else ''}"><h3>{esc(profile['title'])}</h3><p>{esc(profile['description'])}</p><audio controls preload="metadata" aria-label="{esc(profile['title'])}: {esc(row['title'])}" src="{esc(row['audio'])}"></audio><a class="download" href="{esc(row['audio'])}" download>Скачать WAV ↗</a>{check}</section>'''
        cards.append(f'<article><h2>{esc(rows[0]["title"])}</h2><p class="phrase">{esc(rows[0]["text"])}</p><div class="players">{players}</div></article>')
    summary = result['summary']
    checked = any('recognition' in row for row in result['results'])
    status = f'Whisper: {summary["zero_wer"]} из {summary["clips"]} записей без ошибок слов.' if checked else 'Проверка распознавания ещё не выполнена.'
    speed_link = ('<p class="note"><a href="../voice-speed-rms/index.html">Сравнить исходный и ускоренный синтез ↗</a></p>') if (ROOT/'reports/voice-speed-rms/index.html').is_file() else ''
    page = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Scott Voice · Выбор характера</title>
<style>:root{color-scheme:dark;font-family:Segoe UI,system-ui,sans-serif;background:#10141c;color:#edf2f7}*{box-sizing:border-box}body{margin:0}main{max-width:1220px;margin:auto;padding:48px 26px}a{color:#9dc9de;text-decoration:none}a:hover{text-decoration:underline}.brand{font-size:12px;letter-spacing:2px;color:#8cbecf}h1{font-size:40px;margin:18px 0 14px;font-weight:600;letter-spacing:-1px}.lead{max-width:780px;color:#b2becc;line-height:1.7}h2{font-size:21px;font-weight:600;margin:0}h3{font-size:16px;font-weight:600;margin:0 0 10px}.check{color:#b5c9d2;border-left:3px solid #78aabd;padding:12px 18px;background:#182430;margin:24px 0}article{padding:26px;background:#191f29;border:1px solid #303a49;border-radius:20px;margin-top:22px}.phrase{color:#bdc9d5;line-height:1.65;margin:14px 0 22px}.players{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.player{background:#121822;border:1px solid #303a49;border-radius:13px;padding:18px 14px}.player.recommended{border-color:#648e9f;background:#172630}.player p{min-height:64px;color:#a9b9c9;font-size:13px;line-height:1.6;margin:0 0 14px}audio{display:block;width:100%;height:44px}.download{display:inline-block;font-size:12px;margin-top:14px}details{margin-top:16px;font-size:12px;color:#a9becd}summary{cursor:pointer}details p{min-height:0;margin-top:12px}.note{font-size:14px;color:#a9b9c9;line-height:1.7;margin-top:28px}.back{display:inline-block;margin-top:20px;font-size:14px}@media(max-width:980px){.players{grid-template-columns:1fr 1fr}}@media(max-width:540px){main{padding:30px 16px}h1{font-size:32px}article{padding:20px}.players{grid-template-columns:1fr}.player p{min-height:0}}</style>
<main><div class="brand">SCOTT AI / ГОЛОС</div><h1>Scott Voice</h1><p class="lead">Мужской, уверенный и сдержанный голос с цифровым характером. Сравни три степени роботизированной окраски с исходным тембром. Начни с короткого ответа, затем проверь числа и технические названия.</p><p class="check">'''+esc(status)+'''</p>'''+''.join(cards)+'''<p class="note">Громкость записей выровнена. Темп сохранён; высота исходного голоса специально не меняется. Распознавание проверяет слова; приятность тембра, ударения и усталость от звучания оцениваются на слух. Варианты пока доступны для сравнения, рабочий голос приложения остаётся прежним.</p>'''+speed_link+'''<a class="back" href="../voice-base/index.html">← Проверка базового голоса</a></main><script>document.querySelectorAll('audio').forEach(player=>player.addEventListener('play',()=>document.querySelectorAll('audio').forEach(other=>{if(other!==player)other.pause()})));</script></html>'''
    target = args.output/'index.html'
    target.write_text(page, encoding='utf-8')
    print(str(target.resolve()))


if __name__ == '__main__':
    main()
