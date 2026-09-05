"""
Написание, сборка и запуск программ.

Проверки идут на настоящих компиляторах, если те есть на машине, и
пропускаются, если нет: смысл этого модуля в том и состоит, чтобы честно
работать с тем, что установлено, а не с тем, что предполагалось.

Главная ловушка, найденная здесь практикой: gcc из MSYS2 без своего каталога в
PATH завершается с кодом 1 и НЕ печатает ни строчки — ни в stdout, ни в
stderr. Со стороны это выглядит как провал сборки без причины, и понять его,
глядя в код, невозможно.
"""

import pytest

pytestmark = pytest.mark.unit

HELLO_C = r'''#include <stdio.h>

int main(void) {
    printf("Hello, World!\n");
    return 0;
}
'''

BROKEN_C = r'''#include <stdio.h>

int main(void) {
    printf("Hello!\n")
    return 0;
}
'''


@pytest.fixture
def tools(tmp_path, monkeypatch):
    """Модуль с рабочей папкой во временном каталоге."""
    import code_tools

    monkeypatch.setattr(code_tools, "WORKSPACE", tmp_path / "code")
    return code_tools


def needs(tools, language):
    info = tools.inspect(language)
    if not info["available"]:
        pytest.skip(f"на этой машине нет инструментов для {language}")
    return info


# ==================== Распознавание языка ====================

@pytest.mark.parametrize("phrase,expected", [
    ("напиши программу на C которая выводит Hello World", "c"),
    ("напиши на си шарп калькулятор", "csharp"),
    ("напиши на c# консольное приложение", "csharp"),
    ("сделай на c++ сортировку", "cpp"),
    ("напиши на си плюс плюс класс", "cpp"),
    ("напиши скрипт на питоне", "python"),
    ("напиши на джаве класс", "java"),
    ("напиши на js обработчик", "javascript"),
])
def test_language_detection(tools, phrase, expected):
    """
    Язык узнаётся по названию, а не по подстроке.

    Простое вхождение здесь не работает совсем: «c» находится и в «c#», и в
    «c++», и просьба написать на C# уходила компилировать обычный C.
    """
    assert tools.detect_language(phrase) == expected


def test_unnamed_language_is_not_guessed(tools):
    """Если язык не назван, честнее переспросить, чем писать на том, что показалось."""
    assert tools.detect_language("напиши программу") is None


# ==================== Осмотр машины ====================

def test_survey_reports_what_exists(tools):
    """Осмотр перечисляет языки и говорит, какие из них доступны."""
    data = tools.survey()

    assert "languages" in data
    assert set(data["languages"]) == set(tools.TOOLCHAINS)
    for name, info in data["languages"].items():
        assert isinstance(info["available"], bool)
        if not info["available"]:
            assert info["install_hint"], f"для {name} нет подсказки, как поставить"


def test_missing_language_is_rejected(tools):
    assert tools.inspect("брейнфак")["available"] is False


# ==================== Полный путь ====================

def test_write_build_run(tools):
    """
    Программа пишется, собирается и запускается — как её и просили.

    Это тот самый сценарий: «напиши программу на C, которая выводит
    Hello, World!».
    """
    needs(tools, "c")

    saved = tools.save_source(HELLO_C, "c", "hello")
    assert saved["success"]

    built = tools.build(saved["path"], "c")
    assert built["success"], built.get("error")

    result = tools.run(built["binary"], "c")
    assert result["success"], result.get("stderr")
    assert "Hello, World!" in result["output"]


def test_compiler_errors_reach_the_user(tools):
    """
    Ошибка компилятора возвращается человеку целиком.

    По ней видно, что именно не так с кодом — а Scott сможет исправить себя на
    следующем шаге.
    """
    needs(tools, "c")

    saved = tools.save_source(BROKEN_C, "c", "broken")
    built = tools.build(saved["path"], "c")

    assert not built["success"]
    assert built["error"], "компилятор промолчал — значит ему не хватило окружения"
    assert "error" in built["error"].lower()


def test_python_runs_without_build(tools):
    """Интерпретируемый язык не требует сборки — и это не ошибка."""
    needs(tools, "python")

    saved = tools.save_source('print("привет из питона")', "python", "hi")
    built = tools.build(saved["path"], "python")

    assert built["success"]
    assert built["compiled"] is False

    result = tools.run(saved["path"], "python")
    assert "привет из питона" in result["output"]


def test_endless_program_is_stopped(tools, monkeypatch):
    """
    Программа с бесконечным циклом не вешает Scott.

    Без таймаута ассистент замолчал бы навсегда, и человек не понял бы, почему.
    """
    needs(tools, "python")
    monkeypatch.setattr(tools, "RUN_TIMEOUT", 2)

    saved = tools.save_source("while True:\n    pass\n", "python", "endless")
    result = tools.run(saved["path"], "python")

    assert not result["success"]
    assert "цикл" in result["error"] or "секунд" in result["error"]


# ==================== Границы ====================

@pytest.mark.parametrize("name,expected", [
    ("../../../windows/system32/evil", "windows_system32_evil"),
    ("обычное имя", "обычное_имя"),
    ("", "program"),
])
def test_file_names_are_made_safe(tools, name, expected):
    """
    Имя файла не должно уводить запись за пределы рабочей папки.

    Имя приходит из речи, а Whisper выдаёт что угодно — включая слэши.
    """
    assert tools.safe_name(name) == expected


def test_sources_stay_in_workspace(tools):
    """Файлы пишутся только в рабочую папку, как бы ни назвали программу."""
    saved = tools.save_source("print(1)", "python", "../../побег")

    assert saved["success"]
    assert str(tools.WORKSPACE) in saved["path"]


def test_manual_instructions_are_given(tools):
    """
    Для запуска руками есть внятная инструкция.

    Она нужна, когда человек не хочет, чтобы Scott запускал что-то сам, — и
    когда компилятора нет вовсе.
    """
    saved = tools.save_source(HELLO_C, "c", "hello")
    text = tools.manual_instructions(saved["path"], "c")

    assert "gcc" in text
    assert "hello" in text
    assert str(tools.WORKSPACE) in text
