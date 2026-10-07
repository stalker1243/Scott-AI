"""Build a manual listening page for the isolated process's cached short replies."""
from pathlib import Path
import html
import json
import os

ROOT = Path(__file__).resolve().parents[2]


def main():
    report = ROOT/'reports/voice-service'
    result = json.loads((report/'service.json').read_text(encoding='utf-8'))
    cards = []
    for row in result['results']:
        link = os.path.relpath(ROOT/row['audio'],report).replace('\\','/')
        cards.append(f'<article><h2>{html.escape(row["text"])}</h2><audio controls preload="metadata" aria-label="{html.escape(row["text"],quote=True)}" src="{html.escape(link,quote=True)}"></audio><p>{row["seconds"]:.2f} с речи · получение из кеша {row["cache_hit_seconds"]*1000:.2f} мс</p></article>')
    page = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Scott Voice · Короткие ответы</title><style>:root{font-family:Segoe UI,system-ui,sans-serif;color-scheme:dark;background:#10141c;color:#edf2f7}*{box-sizing:border-box}body{margin:0}main{max-width:800px;margin:auto;padding:48px 24px}h1{font-size:32px;font-weight:600}h2{font-size:20px;font-weight:600}p{line-height:1.7;color:#adbece}article{border:1px solid #303a49;background:#191f29;border-radius:18px;padding:22px;margin-top:20px}article p{font-size:13px}audio{width:100%;max-width:460px;height:44px}a{color:#9dc9de;text-decoration:none}.note{font-size:14px;margin:28px 0}@media(max-width:540px){main{padding:28px 18px}}</style><main><h1>Scott Voice: короткие ответы</h1><p>Реплики подготовлены отдельным процессом. После первого синтеза готовые WAV доступны из дискового кеша, в том числе после остановки модели. Воспроизведение начинается по нажатию.</p>'''+''.join(cards)+'''<p class="note">Время кеша измеряет получение проверенного файла, без воспроизведения. Первый синтез требует загрузки модели. Это проверка нового движка; выбор голоса в настройках приложения будет добавлен следующим этапом.</p><a href="../scott-voice/index.html">← Сравнение характера Scott Voice</a></main><script>document.querySelectorAll('audio').forEach(player=>player.addEventListener('play',()=>document.querySelectorAll('audio').forEach(other=>{if(other!==player)other.pause()})));</script></html>'''
    (report/'index.html').write_text(page,encoding='utf-8')
    print(str((report/'index.html').resolve()))


if __name__=='__main__':
    main()
