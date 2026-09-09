"""
Куда уходит фраза: снимок решений маршрутизации.

Решение о том, что значит сказанное, принимается сейчас в трёх местах сразу —
`fast_intent`, `command_parser` и `question_answerer.is_question` — а `main.py`
мирит их между собой полудюжиной заплаток. Прежде чем сводить это воедино,
нужно знать, что именно происходит сегодня: иначе любая правка превращается в
угадывание.

Здесь исполнение заглушено — ни сети, ни запуска программ, ни файлов на диске.
Записывается только ветка, в которую ушла фраза, и с каким параметром.

Запуск:
    python tests/routing_probe.py            — показать таблицу
    python tests/routing_probe.py --save     — записать снимок в routing_snapshot.txt
"""

import os
import sys
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

os.environ.setdefault("WARMUP_MODELS", "0")

SNAPSHOT = HERE / "routing_snapshot.txt"


def _quiet_imports():
    """Прогреть тяжёлые модули, пока их болтовня никому не мешает."""
    import io
    import contextlib

    with contextlib.redirect_stdout(io.StringIO()):
        import main
        return main


def collect() -> list:
    """Прогнать все фразы и записать, куда каждая ушла."""
    import asyncio
    import contextlib
    import io

    main = _quiet_imports()
    from routing_phrases import ВСЕ_ФРАЗЫ

    scott = main.scott_ai

    # Всё подменённое возвращается на место. Модули общие на весь процесс, и
    # оставленная болванка ломает следующие тесты — так уже случилось с
    # проверками веб-интеграций, которые шли после снимка.
    with _stubs(main, scott):
        rows = []
        for phrase in ВСЕ_ФРАЗЫ:
            with contextlib.redirect_stdout(io.StringIO()):
                result = asyncio.run(scott.process_command(phrase, quiet_mode=True))

            kind = result.get("type", "?")
            response = (result.get("response") or "").replace("\n", " ")
            command = result.get("command", "")
            rows.append((phrase, kind, command, response))

    return rows


@contextmanager
def _stubs(main, scott):
    """
    Заглушить всё, что имеет последствия: сеть, запуск программ, запись файлов.

    Интересует только решение — в какую ветку ушла фраза, — а не то, что
    случится дальше.
    """
    class _Тихий:
        enabled = True
        model = "<модель>"

        def answer_question(self, text):
            return "<ответ ИИ>"

        def answer(self, text, use_memory=False):
            return "<ответ ИИ>", True

    async def _выполнить(parsed, original_text):
        return f"<выполнено: {parsed.command_type} / {parsed.main_param}>"

    подмены = [
        (main.knowledge_base, "search_memory", lambda text: {}),
        (main.knowledge_base, "add_conversation", lambda *a, **k: None),
        (main.question_answerer, "answer", lambda text: "<локальный ответ>"),
        (main.web_integrations, "search_youtube_video",
         lambda q: {"message": f"<ютуб: поиск «{q}»>"}),
        (main.web_integrations, "search_github_repo",
         lambda q: {"message": f"<гитхаб: поиск «{q}»>"}),
        (main.web_integrations, "open_service_home",
         lambda s: {"message": f"<{s}: открыт сайт>"}),
        (main, "intelligent_answerer", _Тихий()),
        (main.scott_runtime, "intelligent_answerer", _Тихий()),
        (scott, "_execute_parsed_command", _выполнить),
    ]

    # Часть имён появляется у модулей только во время работы, а не при
    # загрузке. Отсутствие запоминаем отдельной меткой, чтобы на обратном пути
    # убрать заглушку совсем, а не оставить её под видом «исходного значения».
    ОТСУТСТВОВАЛО = object()

    было = [(obj, name, getattr(obj, name, ОТСУТСТВОВАЛО)) for obj, name, _ in подмены]
    for obj, name, replacement in подмены:
        setattr(obj, name, replacement)

    try:
        yield
    finally:
        for obj, name, original in было:
            if original is ОТСУТСТВОВАЛО:
                try:
                    delattr(obj, name)
                except AttributeError:
                    pass
            else:
                setattr(obj, name, original)


def render(rows) -> str:
    lines = []
    for phrase, kind, command, response in rows:
        label = f"{kind}/{command}" if command else kind
        lines.append(f"{phrase}\n    -> {label}: {response}")
    return "\n".join(lines) + "\n"


def main_cli():
    rows = collect()
    text = render(rows)

    if "--save" in sys.argv:
        SNAPSHOT.write_text(text, encoding="utf-8")
        print(f"Снимок записан: {SNAPSHOT} ({len(rows)} фраз)")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)


if __name__ == "__main__":
    main_cli()
