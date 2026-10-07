"""Build an offline page for the selected voice's Base 0.6B trial recordings."""
from pathlib import Path
import argparse
import html
import json

from trial_utils import ROOT


def esc(value):
    return html.escape(str(value), quote=True)


def player(row, label):
    recognition = row.get('recognition')
    check = ''
    if recognition:
        check = (f'<details><summary>Распознанный текст · ошибки слов {recognition["word_error_rate"]*100:.1f}%</summary>'
                 f'<p>{esc(recognition["heard"])}</p></details>')
    return f'''<div class="player"><h3>{esc(label)}</h3>
    <audio controls preload="metadata" aria-label="{esc(label)}: {esc(row['title'])}" src="{esc(row['audio'])}"></audio>
    <div class="metrics"><span>{row['seconds']:.1f} с речи · {row['synthesis_seconds']:.2f} с генерации</span><a href="{esc(row['audio'])}" download>WAV ↗</a></div>{check}</div>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/voice-base')
    args = parser.parse_args()
    base = json.loads((args.output/'base.json').read_text(encoding='utf-8'))
    silero = {row['id']: row for row in json.loads((args.output/'silero.json').read_text(encoding='utf-8'))['results']}
    cards = []
    for row in base['results']:
        cards.append(f'''<article><div class="heading"><span class="number">0{len(cards)+1}</span><h2>{esc(row['title'])}</h2></div>
        <p class="phrase">{esc(row['text'])}</p><div class="players">{player(row,'Новый голос · Base 0.6B')}{player(silero[row['id']],'Текущий голос · Евгений / Спокойный')}</div></article>''')
    summary = base.get('summary', {})
    zero_wer = sum(bool(row.get('recognition', {}).get('success')) and row['recognition']['word_error_rate']==0 for row in base['results'])
    checks = f'{summary.get("zero_wer", zero_wer)} из {summary.get("cases", len(cards))}'
    concurrency = base.get('monitor', {})
    health = concurrency.get('health_p95_seconds')
    peak = concurrency.get('gpu_observed_used_peak_gib')
    status = (f'<p>Во время совместной проверки: /health, 95% ответов ≤ {health:.3f} с. '
              f'Наблюдавшийся расход видеопамяти всех процессов и рабочего стола — до {peak:.2f} ГиБ.</p>') if health is not None and peak is not None else ''
    scott_voice = ('<section class="reference"><h2>Scott Voice</h2><p><a href="../scott-voice/index.html">Сравнить три степени роботизированного звучания ↗</a></p></section>') if (ROOT/'reports/scott-voice/index.html').is_file() else ''
    greedy = base.get('greedy_control')
    control = ''
    if greedy:
        if greedy.get('recognition', {}).get('success'):
            control = '<article><div class="heading"><h2>Дополнительная проба скорости</h2></div><p class="phrase">Исходный текст, генерация без случайного выбора звуковых токенов. Сравни с первой репликой: изменения темпа и интонации возможны.</p>'+player(greedy,'Base 0.6B · без случайного выбора')+'</article>'
        else:
            control = '<details class="note"><summary>Дополнительная проба скорости</summary><p>Режим без случайного выбора токенов дал почти тихий сигнал и достиг ограничения длины. Выбран обычный режим генерации, представленный в шести репликах выше.</p></details>'
    page = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Scott · Проверка нового голоса</title><style>
    :root{color-scheme:dark;font-family:Segoe UI,system-ui,sans-serif;background:#10121a;color:#eef0f7}*{box-sizing:border-box}body{margin:0}main{max-width:1060px;margin:auto;padding:56px 28px}a{color:#a7b6fc;text-decoration:none}a:hover{text-decoration:underline}.brand{color:#a7b6fc;letter-spacing:2px;font-size:13px;margin-bottom:26px}h1{font-size:36px;font-weight:600;letter-spacing:-.8px;margin:0 0 16px}h2{font-size:21px;font-weight:600;margin:0}h3{font-size:14px;font-weight:500;color:#b9c5ed;margin:0 0 14px}p{line-height:1.65}.lead{color:#b3b8c9;max-width:780px}.reference{padding:22px 24px;background:#151b2c;border:1px solid #38456a;border-radius:18px;margin:28px 0 24px}.reference audio{max-width:430px;margin-top:14px}.reference p{color:#b9c5dd;font-size:14px;margin:10px 0 0}
    article{background:#191c28;border:1px solid #2c3042;border-radius:20px;padding:26px;margin-top:20px;transition:border-color .2s}article.playing{border-color:#95a7ff}.heading{display:flex;gap:16px;align-items:center}.number{font-size:13px;color:#8492c7}.phrase{color:#b6bfd3;font-size:15px;margin:18px 0 26px}.players{display:grid;grid-template-columns:1fr 1fr;gap:26px}.player{min-width:0}audio{width:100%;height:44px}.metrics{display:flex;justify-content:space-between;gap:10px;color:#9aa5bf;font-size:12px;margin-top:12px}.metrics a{flex-shrink:0}details{font-size:13px;margin-top:17px;color:#aab6d5}summary{cursor:pointer}details p{color:#c2cadb}.note{margin-top:28px;color:#99a3ba;font-size:14px}.back{display:inline-block;margin-top:22px;font-size:14px}.stats{display:flex;flex-wrap:wrap;gap:12px;margin:22px 0}.stat{background:#20263a;border-radius:12px;padding:13px 17px;color:#b9c5e8;font-size:14px}
    @media(max-width:720px){main{padding:32px 18px}h1{font-size:29px}.players{grid-template-columns:1fr;gap:24px}article{padding:22px}.metrics{flex-wrap:wrap}}
    @media(prefers-reduced-motion:reduce){article{transition:none}}
    </style><main><div class="brand">SCOTT AI / НОВЫЙ ГОЛОС</div><h1>«Чуть строгий» на новых репликах</h1>
    <p class="lead">Base 0.6B создаёт новые реплики по выбранному эталону. Сравни произношение, паузы и характер с текущим голосом на одинаковых фразах. Звук начинается после нажатия.</p>
    <section class="reference"><h2>Выбранный эталон</h2><p>Уверенный и сдержанный голос из первого сравнения.</p><audio controls preload="metadata" aria-label="Выбранный эталон Чуть строгий" src="../voice-design/reference/scott-reference.wav"></audio></section>
    <div class="stats"><div class="stat">Без ошибок слов: '''+esc(checks)+''' реплик</div><div class="stat">Загрузка Base: '''+f'{base["load_seconds"]:.2f}'+''' с</div><div class="stat">Подготовка эталона: '''+f'{base["prompt_seconds"]:.2f}'+''' с</div></div>'''+scott_voice+''.join(cards)+control+'''<section class="note"><p>Скорость указана после отдельного прогрева. Это время создания полной записи: воспроизведение по частям пока не измерялось. Автоматическое распознавание проверяет слова; ударения и тембр нужно оценить на слух.</p>'''+status+'''</section><a class="back" href="../voice-design/index.html">← Первое сравнение голосов</a></main>
    <script>document.querySelectorAll('audio').forEach(player=>{player.addEventListener('play',()=>{document.querySelectorAll('audio').forEach(other=>{if(other!==player)other.pause()});player.closest('article')?.classList.add('playing')});['pause','ended'].forEach(event=>player.addEventListener(event,()=>player.closest('article')?.classList.remove('playing')))});</script></html>'''
    target = args.output/'index.html'
    target.write_text(page, encoding='utf-8')
    print(str(target.resolve()))


if __name__ == '__main__':
    main()
