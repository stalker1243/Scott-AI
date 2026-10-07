"""Create an offline audio comparison page from generated sample metadata."""
from pathlib import Path
import argparse
import html
import hashlib
import json
import os

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/voice-design')
    args = parser.parse_args()
    samples = json.loads((args.output/'samples.json').read_text(encoding='utf-8'))
    recognition = args.output/'recognition.json'
    checks = {row['profile']: row for row in json.loads(recognition.read_text(encoding='utf-8'))['results']} if recognition.exists() else {}
    baseline_file = args.output/'baseline.json'
    baseline = json.loads(baseline_file.read_text(encoding='utf-8')) if baseline_file.exists() else None
    selection_file = args.output/'selection.json'
    selection = json.loads(selection_file.read_text(encoding='utf-8')) if selection_file.exists() else None
    if selection:
        selected_audio = args.output/selection['source_audio']
        if not selected_audio.is_file() or hashlib.sha256(selected_audio.read_bytes()).hexdigest() != selection['sha256']:
            selection = None
    cards = []
    for row in samples['results']:
        check = checks.get(row['profile'])
        transcript = ('<details><summary>Распознанный текст</summary><p>'+html.escape(check['heard'])+'</p></details>') if check else ''
        chosen = bool(selection and selection['profile'] == row['profile'])
        badge = '<span class="badge">Выбран для Scott</span>' if chosen else ''
        cards.append(f'''<article class="card{' selected' if chosen else ''}">
          <div class="number"><span>0{len(cards)+1}</span>{badge}</div>
          <h2>{html.escape(row['title'])}</h2>
          <p class="description">{html.escape(row['description'])}</p>
          <audio controls preload="metadata" aria-label="Голос: {html.escape(row['title'])}" src="{html.escape(row['audio'])}"></audio>
          <div class="footer"><span>{row['seconds']:.1f} с</span><a href="{html.escape(row['audio'])}" download>Скачать WAV ↗</a></div>
          {transcript}
        </article>''')
    reference_player = (f'<section class="text"><h2>Текущий голос для сравнения</h2><p>Евгений, спокойная подача. Тот же текст и сопоставимая громкость.</p><audio controls preload="metadata" aria-label="Текущий голос Евгений" src="{html.escape(baseline["audio"])}"></audio></section>') if baseline else ''
    base_page = ROOT/'reports/voice-base/index.html'
    next_stage = ('<section class="text"><h2>Выбранный голос на новых репликах</h2><p><a href="'+html.escape(os.path.relpath(base_page, args.output).replace('\\','/'))+'">Открыть проверку Base 0.6B и сравнение с текущим голосом ↗</a></p></section>') if base_page.exists() else ''
    scott_page = ROOT/'reports/scott-voice/index.html'
    if scott_page.is_file():
        next_stage += '<section class="text"><h2>Scott Voice</h2><p><a href="'+html.escape(os.path.relpath(scott_page, args.output).replace('\\','/'))+'">Сравнить роботизированные варианты ↗</a></p></section>'
    page = '''<!doctype html><html lang="ru"><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"><title>Голос Scott</title>
    <style>
    :root{color-scheme:dark;font-family:Segoe UI,system-ui,sans-serif;color:#eef0f7;background:#10121a}
    *{box-sizing:border-box}body{margin:0}main{max-width:1120px;margin:auto;padding:64px 28px}
    .brand{font-size:13px;letter-spacing:2px;color:#a7b6fc;margin-bottom:28px}h1{font-size:42px;letter-spacing:-1px;margin:0 0 14px;font-weight:600}
    .lead{font-size:17px;line-height:1.6;max-width:720px;color:#b3b8c9;margin-bottom:36px}
    .grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}.card{background:#191c28;border:1px solid #2c3042;border-radius:20px;padding:24px;transition:border-color .2s,background .2s}
    .card.selected{border-color:#7084d5}.card.playing{border-color:#95a7ff;background:#20263a}.badge{display:inline-block;background:#283451;color:#c5d2ff;font-size:12px;padding:5px 9px;border-radius:8px}.number{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:27px;color:#8492c7;font-size:13px;margin-bottom:22px}h2{font-size:23px;font-weight:600;margin:0 0 12px}.description{color:#adb4c6;line-height:1.55;min-height:54px;font-size:15px;margin-bottom:26px}
    audio{width:100%;height:44px}.footer{display:flex;justify-content:space-between;gap:12px;font-size:13px;color:#aab1c3;margin-top:16px}a{color:#a7b6fc;text-decoration:none}a:hover{text-decoration:underline}
    .text{margin-top:32px;padding:26px;background:#151822;border:1px solid #282c3c;border-radius:20px}.text h2{font-size:16px;color:#c3cade}.text p{color:#bac1d1;line-height:1.75;margin-bottom:0}.text audio{margin-top:16px;max-width:420px}
    .note{color:#8991a7;font-size:14px;line-height:1.65;margin-top:24px;max-width:780px}details{border-top:1px solid #30364a;margin-top:22px;padding-top:16px;font-size:13px;color:#abb5d3}summary{cursor:pointer}details p{line-height:1.65;color:#c7cddd}
    @media(max-width:850px){.grid{grid-template-columns:1fr}.description{min-height:0}.number{margin-bottom:12px}main{padding:36px 20px}h1{font-size:34px}}
    @media(prefers-reduced-motion:reduce){.card{transition:none}}
    </style><main><div class="brand">SCOTT AI / ГОЛОС</div><h1>Как будет звучать Scott?</h1>
    <p class="lead">Три мужских голоса с разной подачей. Сравни их на одинаковом тексте: разборчивость, тембр, паузы и окончания слов.</p>
    <section class="grid">''' + ''.join(cards) + '''</section>''' + next_stage + reference_player + '''<section class="text"><h2>Текст образца</h2><p>''' + html.escape(samples['reference']) + '''</p></section>
    <p class="note">Прослушай в привычных наушниках или колонках. Автоматическая проверка помогает заметить пропущенные слова; тембр и ударения оценивай на слух. Записи воспроизводятся локально.</p></main>
    <script>document.querySelectorAll('audio').forEach(player=>{
      player.addEventListener('play',()=>{document.querySelectorAll('audio').forEach(other=>{if(other!==player)other.pause()});player.closest('.card')?.classList.add('playing')});
      ['pause','ended'].forEach(event=>player.addEventListener(event,()=>player.closest('.card')?.classList.remove('playing')));
    });</script></html>'''
    target = args.output/'index.html'
    target.write_text(page, encoding='utf-8')
    print(str(target.resolve()))


if __name__ == '__main__':
    main()
