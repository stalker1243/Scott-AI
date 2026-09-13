"""
Backend должен существовать в одном экземпляре.

Scott запускается как «python main.py», и тогда главный файл выполняется под
именем `__main__`. Но соседние модули обращаются к нему как `import main` — и
Python, не узнав в этом имени уже выполняющийся файл, честно выполняет его
ВТОРОЙ раз. Получаются две копии backend со своими наборами глобальных
переменных: два набора менеджеров, два слушателя, два `_main_loop`.

Снаружи это выглядело как «Scott слышит, но молчит». Микрофон писал, Whisper
распознавал, обращение по имени срабатывало — а дальше команда уходила в копию,
где главный цикл никогда не поднимался, и терялась без единой строчки в логе.
Найти это удалось только напечатав `__name__` прямо из обработчика.

Обе защиты проверяются здесь, потому что каждая по отдельности дырявая: новый
`import main` в любом модуле вернёт двойника, если псевдоним не поставлен, а
псевдоним не поможет тому, кто импортирует main до его установки.
"""

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

BACKEND = Path(__file__).resolve().parent.parent


def test_warming_speech_cache_does_not_import_backend():
    """
    Прогрев голосового кэша не тянет за собой весь backend.

    Ему нужны три коротких слова («Секунду», «Минуту», «Сейчас посмотрю»), и
    ради них он импортировал main целиком. Это и заводило вторую копию.

    Проверка идёт в отдельном процессе: в общей сессии main почти наверняка
    уже импортирован другими тестами, и подмены не будет видно.
    """
    код = (
        "import sys, speech_cache; "
        "speech_cache.stock_phrases(); "
        "print('MAIN' if 'main' in sys.modules else 'ЧИСТО')"
    )

    готово = subprocess.run(
        [sys.executable, "-c", код],
        cwd=BACKEND, capture_output=True, text=True, encoding="utf-8", timeout=180,
    )

    assert "ЧИСТО" in (готово.stdout or ""), (
        "прогрев кэша импортировал main — при запуске «python main.py» это "
        f"заведёт вторую копию backend.\n{готово.stdout}\n{готово.stderr}"
    )


def test_thinking_cues_live_outside_main():
    """Реплики «секунду» лежат там, откуда их можно взять дёшево."""
    from speech_text import THINKING_CUES

    assert THINKING_CUES, "набор пуст"
    assert all(isinstance(ф, str) and ф.strip() for ф in THINKING_CUES)


def test_main_claims_its_name_before_importing_neighbours():
    """
    Псевдоним ставится раньше первого импорта соседа.

    Он спасает и от будущих «import main»: тот вернёт уже выполняющуюся копию
    вместо новой. Но только если успел появиться до того, как сосед спросит, —
    иначе порядок строк тихо отменяет всю защиту, и поломка возвращается в том
    же неотличимом виде.
    """
    строки = (BACKEND / "main.py").read_text(encoding="utf-8").splitlines()

    псевдоним = next(
        (n for n, с in enumerate(строки) if 'sys.modules.setdefault("main"' in с),
        None,
    )
    assert псевдоним is not None, (
        "в main.py нет псевдонима sys.modules.setdefault(\"main\", ...) — "
        "«import main» в любом соседнем модуле заведёт вторую копию backend"
    )

    # Первый импорт модуля, лежащего рядом с main.py.
    соседи = {ф.stem for ф in BACKEND.glob("*.py")} - {"main"}

    def сосед(строка: str) -> bool:
        слова = строка.split()
        if not слова or слова[0] not in ("import", "from"):
            return False
        return слова[1].split(".")[0] in соседи

    первый = next((n for n, с in enumerate(строки) if сосед(с)), len(строки))

    assert псевдоним < первый, (
        f"псевдоним стоит в строке {псевдоним + 1}, а сосед импортируется уже в "
        f"{первый + 1}: «{строки[первый].strip()}». Тот получит вторую копию."
    )
