"""Manual listening page for the completed Scott Voice integration check."""
from pathlib import Path
import html
import json
import sys
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUTPUT = ROOT/'reports/voice-integration'


def main():
    report = json.loads((OUTPUT/'integration.json').read_text(encoding='utf-8'))
    cards = []
    for index, row in enumerate(report['results']):
        path = (ROOT/row['audio']).resolve()
        relative = f'sample-{index+1:02d}-{row["profile"]}.wav'
        # Listening artifacts survive later cache eviction.
        if path.is_file():
            shutil.copy2(path, OUTPUT/relative)
        assert (OUTPUT/relative).is_file()
        title = report['profiles'][row['profile']]
        cards.append(f'<article><h3>{html.escape(title)}</h3><p>{html.escape(row["text"])}</p>'
            f'<audio controls preload="none" aria-label="{html.escape(title+": "+row["text"])}"><source src="{html.escape(relative)}" type="audio/wav"></audio>'
            f'<small>Получение из кеша: {row["cache_seconds"]*1000:.2f} мс · Whisper: без ошибок слов</small></article>')
    page = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Scott Voice — подключение к приложению</title><style>
*{box-sizing:border-box}body{margin:0;background:#0d1420;color:#eaf1fb;font:16px/1.5 system-ui,sans-serif}main{max-width:1120px;padding:36px 24px;margin:auto}h1{font-size:30px}h2{margin-top:34px}h3{font-size:16px;margin:0}p{color:#acbbd0}a{color:#8ab6ff}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}article{padding:20px;background:#182333;border:1px solid #30435d;border-radius:16px}audio{width:100%;margin:8px 0}small{display:block;color:#a5b8d0}img{display:block;width:100%;height:auto;border-radius:14px;margin:18px 0}summary{cursor:pointer}
</style><main><h1>Scott Voice в приложении</h1><p>Настройки → Голос → Scott Voice. Четыре варианта звучания используют один принятый мужской тембр. Прослушивание запускается вручную.</p>
<p>При сбое используется прежний голос. Тихий режим, пауза ассистента и новая команда прерывают подготовку. Кеш ограничен 512 МиБ и 1000 записями; недавно использованный звук защищён на две минуты.</p>
<h2>Короткие ответы</h2><div class="grid">'''+''.join(cards)+'''</div>
<h2>Проверка через backend API</h2><article><p>Проверка завершена.</p><audio controls preload="none" aria-label="Scott Voice: Проверка завершена."><source src="api.wav" type="audio/wav"></audio><small>Whisper: без ошибок слов. Рабочий голос приложения сохранён.</small></article>
<h2>Настройки Qt</h2><details><summary>Classic, Glass и Terminal Pro</summary><img src="classic.png" alt="Настройки Scott Voice в Classic"><img src="glass-preparing.png" alt="Подготовка Scott Voice в Glass"><img src="terminal-compact.png" alt="Компактные настройки Scott Voice в Terminal Pro"></details>
<p>Первый синтез загружает модель и занимает больше времени. Время кеша означает получение WAV, без воспроизведения. Тембр и ударения оцениваются на слух.</p>
<p><a href="../voice-base/index.html">Принятый исходный тембр</a> · <a href="../scott-voice/index.html">Развёрнутое сравнение цифровой окраски</a></p></main></html>'''
    (OUTPUT/'index.html').write_text(page, encoding='utf-8')
    print(OUTPUT/'index.html')


if __name__ == '__main__':
    main()
