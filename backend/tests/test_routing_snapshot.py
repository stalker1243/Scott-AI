"""
Куда уходит фраза: снимок решений маршрутизации.

Решение о том, что значит сказанное, принимается сейчас в трёх местах сразу —
`fast_intent`, `command_parser` и `question_answerer.is_question`, — а `main.py`
мирит их между собой полудюжиной заплаток. Из-за этого правка в одном месте
неслышно меняет поведение в другом: так «закрой дискорд» стало запускать
дискорд, а «привет, что такое фотосинтез» — отвечать заготовкой.

Этот снимок держит всю картину целиком. Он не судит, правильно ли Scott
поступает, — он замечает, что поступать он стал иначе. Изменение в снимке
означает одно из двух: либо это то, чего добивались, и снимок пора обновить,
либо правка задела чужую фразу, и об этом лучше узнать сейчас.

Исполнение заглушено: ни сети, ни запуска программ, ни файлов на диске.

Обновить снимок осознанно:
    python tests/routing_probe.py --save
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SNAPSHOT = Path(__file__).parent / "routing_snapshot.txt"


def test_routing_matches_snapshot():
    """Фразы уходят туда же, куда уходили вчера."""
    import routing_probe

    current = routing_probe.render(routing_probe.collect())
    saved = SNAPSHOT.read_text(encoding="utf-8")

    if current == saved:
        return

    # Показываем только разошедшиеся строки: сравнивать сто строк глазами
    # бессмысленно, а разница обычно в двух-трёх.
    current_map = _by_phrase(current)
    saved_map = _by_phrase(saved)

    changes = []
    for phrase, was in saved_map.items():
        now = current_map.get(phrase, "<фраза исчезла из списка>")
        if now != was:
            changes.append(f"  «{phrase}»\n      было:  {was}\n      стало: {now}")

    for phrase, now in current_map.items():
        if phrase not in saved_map:
            changes.append(f"  «{phrase}» — новая фраза\n      стало: {now}")

    pytest.fail(
        "Маршрутизация изменилась:\n\n" + "\n".join(changes) +
        "\n\nЕсли так и задумано — обновите снимок:\n"
        "    python tests/routing_probe.py --save"
    )


def _by_phrase(text: str) -> dict:
    """Разобрать снимок в пары «фраза → решение»."""
    result = {}
    phrase = None
    for line in text.splitlines():
        if line.startswith("    -> "):
            if phrase is not None:
                result[phrase] = line[len("    -> "):]
        elif line.strip():
            phrase = line
    return result
