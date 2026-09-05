"""
Что на этой машине умеет собирать и запускать код.

Прежде чем обещать «напишу программу и запущу», нужно знать, чем именно. На
одном компьютере стоит MinGW, на другом — только Visual Studio, на третьем нет
ничего, кроме Python. Обещание, которое некому выполнить, хуже честного «у вас
не установлен компилятор C, вот как его поставить».

Языки описаны данными, а не ветвлениями: добавить ещё один — значит дописать
запись в словарь, а не править логику в трёх местах.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# Куда складываются написанные Scott программы.
#
# Отдельная папка в профиле пользователя, а не временный каталог: человек
# захочет посмотреть, что получилось, открыть в редакторе, доделать. Временные
# файлы для этого не годятся — их вычищает система.
WORKSPACE = Path.home() / "ScottAI" / "code"


@dataclass
class Toolchain:
    """Один способ выполнить код: язык, чем собирать, чем запускать."""

    language: str
    display: str
    extension: str
    # Кандидаты в порядке предпочтения: первый найденный и берём.
    compilers: List[str] = field(default_factory=list)
    # Интерпретируемые языки не компилируются — сразу запускаются.
    interpreters: List[str] = field(default_factory=list)
    install_hint: str = ""

    @property
    def compiled(self) -> bool:
        return bool(self.compilers)


TOOLCHAINS: Dict[str, Toolchain] = {
    "c": Toolchain(
        language="c",
        display="C",
        extension=".c",
        compilers=["gcc", "clang", "cc"],
        install_hint="Установите MinGW-w64 (Windows) или пакет build-essential (Linux)",
    ),
    "cpp": Toolchain(
        language="cpp",
        display="C++",
        extension=".cpp",
        compilers=["g++", "clang++"],
        install_hint="Установите MinGW-w64 (Windows) или пакет build-essential (Linux)",
    ),
    "python": Toolchain(
        language="python",
        display="Python",
        extension=".py",
        interpreters=["python", "python3", "py"],
        install_hint="Установите Python с python.org",
    ),
    "javascript": Toolchain(
        language="javascript",
        display="JavaScript",
        extension=".js",
        interpreters=["node"],
        install_hint="Установите Node.js с nodejs.org",
    ),
    "java": Toolchain(
        language="java",
        display="Java",
        extension=".java",
        compilers=["javac"],
        interpreters=["java"],
        install_hint="Установите JDK (например, Temurin)",
    ),
    "csharp": Toolchain(
        language="csharp",
        display="C#",
        extension=".cs",
        interpreters=["dotnet"],
        install_hint="Установите .NET SDK с dotnet.microsoft.com",
    ),
}

# Как человек называет язык вслух. Whisper пишет «си», «си шарп», «плюс плюс» —
# распознавать нужно именно это, а не только каноничные имена.
#
# Каждое название — регулярное выражение с границами, а не подстрока. Простое
# вхождение здесь не работает совсем: «c» находится в «c#» и в «c++», и просьба
# написать на C# уходила компилировать обычный C. Порядок тоже значим — сначала
# проверяются самые длинные и точные названия.
LANGUAGE_PATTERNS = [
    ("csharp", r"c\s*#|си\s*шарп|c\s*sharp|шарп|дотнет|\.net"),
    ("cpp", r"c\s*\+\+|си\s*плюс\s*плюс|плюс\s*плюс|плюсах|cpp"),
    ("javascript", r"\bjava\s*script\b|\bджава\s*скрипт\b|\bяваскрипт\b|\bjs\b|\bnode\b"),
    ("java", r"\bjava\b|\bджав\w*|\bяв[аеу]\b"),
    ("python", r"\bpython\b|\bпитон\w*|\bпайтон\w*"),
    ("c", r"\bc\b|\bси\b|\bсишк\w*"),
]


def detect_language(text: str) -> Optional[str]:
    """
    Узнать в просьбе язык программирования.

    Возвращает None, если язык не назван: тогда честнее переспросить, чем
    писать на том, что показалось.
    """
    lowered = text.lower()

    for language, pattern in LANGUAGE_PATTERNS:
        if re.search(pattern, lowered, re.IGNORECASE):
            return language
    return None


def find_tool(candidates: List[str]) -> Optional[str]:
    """Первый доступный инструмент из списка."""
    for name in candidates:
        if shutil.which(name):
            return name
    return None


def tool_version(tool: str) -> str:
    """Версия инструмента — её показывают пользователю, чтобы он видел, чем собирают."""
    # Флаги перебираются, потому что единого нет: gcc понимает --version,
    # java — только -version и на двойное тире ругается. Ответ-жалобу нужно
    # отличать от настоящей версии, иначе в интерфейс попадёт
    # «Unrecognized option: --version» вместо номера.
    complaints = ("unrecognized", "unknown option", "usage:", "invalid option")

    for flag in ("--version", "-version", "/?"):
        try:
            result = subprocess.run([tool, flag], capture_output=True, text=True, timeout=10)
            output = (result.stdout or result.stderr).strip()
            if not output:
                continue
            first = output.splitlines()[0]
            if any(word in first.lower() for word in complaints):
                continue
            return first[:120]
        except Exception:
            continue
    return "версия неизвестна"


def inspect(language: str) -> Dict:
    """Что доступно для конкретного языка."""
    chain = TOOLCHAINS.get(language)
    if chain is None:
        return {"available": False, "message": f"Не знаю язык «{language}»"}

    compiler = find_tool(chain.compilers) if chain.compilers else None
    interpreter = find_tool(chain.interpreters) if chain.interpreters else None

    available = bool(compiler) if chain.compiled else bool(interpreter)
    # У Java нужны оба: javac собирает, java запускает.
    if chain.compilers and chain.interpreters:
        available = bool(compiler) and bool(interpreter)

    return {
        "language": language,
        "display": chain.display,
        "available": available,
        "compiler": compiler,
        "interpreter": interpreter,
        "version": tool_version(compiler or interpreter) if (compiler or interpreter) else "",
        "install_hint": chain.install_hint,
    }


def survey() -> Dict:
    """
    Полная картина: на чём эта машина может писать и запускать программы.

    Показывается пользователю, когда он спрашивает «а что ты умеешь
    компилировать» — и используется, чтобы не обещать невозможного.
    """
    languages = {name: inspect(name) for name in TOOLCHAINS}
    return {
        "workspace": str(WORKSPACE),
        "languages": languages,
        "available": [name for name, info in languages.items() if info["available"]],
    }


# ==================== Сборка и запуск ====================
#
# Здесь Scott выполняет код, который сам же написал, — и это требует границ.
# Они не в том, чтобы анализировать код на «опасность»: такая проверка
# обманывает себя, а не злоумышленника. Границы простые и честные:
#
# * файлы пишутся только в рабочую папку в профиле пользователя;
# * запуск идёт с таймаутом, иначе бесконечный цикл в программе повесит Scott;
# * запускается ровно то, что человек видел, и только по отдельной просьбе.

RUN_TIMEOUT = 20
BUILD_TIMEOUT = 60


def _tool_env(tool: str) -> Dict[str, str]:
    """
    Окружение, в котором компилятор находит свои вспомогательные программы.

    Каталог самого компилятора добавляется в PATH, и это не перестраховка:
    gcc из MSYS2 без него не находит cc1.exe и завершается с кодом 1, НЕ
    напечатав ни строчки — ни в stdout, ни в stderr. Со стороны выглядит так,
    будто сборка провалилась без причины.
    """
    env = dict(os.environ)
    location = shutil.which(tool)
    if location:
        folder = str(Path(location).parent)
        env["PATH"] = folder + os.pathsep + env.get("PATH", "")
    return env


def safe_name(name: str) -> str:
    """Превратить произвольное имя в безопасное имя файла."""
    cleaned = re.sub(r"[^\w\-.]+", "_", name.strip(), flags=re.UNICODE)
    cleaned = cleaned.strip("._") or "program"
    return cleaned[:60]


def save_source(code: str, language: str, name: str = "program") -> Dict:
    """Записать исходник в рабочую папку и вернуть путь."""
    chain = TOOLCHAINS.get(language)
    if chain is None:
        return {"success": False, "error": f"Не знаю язык «{language}»"}

    try:
        WORKSPACE.mkdir(parents=True, exist_ok=True)
        path = WORKSPACE / f"{safe_name(name)}{chain.extension}"
        path.write_text(code, encoding="utf-8")
    except OSError as e:
        return {"success": False, "error": f"Не удалось сохранить файл: {e}"}

    return {"success": True, "path": str(path), "language": language}


def build(source_path: str, language: str) -> Dict:
    """
    Собрать программу.

    Для интерпретируемых языков сборки нет — это не ошибка, а нормальный
    случай, поэтому возвращается успех с пометкой.
    """
    chain = TOOLCHAINS.get(language)
    if chain is None:
        return {"success": False, "error": f"Не знаю язык «{language}»"}

    if not chain.compilers:
        return {"success": True, "compiled": False, "message": "Этот язык не требует сборки"}

    compiler = find_tool(chain.compilers)
    if compiler is None:
        return {
            "success": False,
            "error": f"Не нашёл компилятор для {chain.display}. {chain.install_hint}",
        }

    source = Path(source_path)
    binary = source.with_suffix(".exe" if os.name == "nt" else "")

    if language == "java":
        command = [compiler, str(source)]
        binary = source.with_suffix(".class")
    else:
        command = [compiler, str(source), "-o", str(binary)]

    try:
        result = subprocess.run(
            command, capture_output=True, text=True,
            timeout=BUILD_TIMEOUT, cwd=str(source.parent),
            env=_tool_env(compiler),
            # Явная кодировка обязательна: text=True читает вывод в кодировке
            # консоли, а компиляторы пишут в UTF-8. Из-за этого сообщения об
            # ошибках с русскими комментариями приходили нечитаемыми — а
            # показывать их человеку нужно именно такими, как есть.
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Сборка затянулась дольше минуты"}
    except Exception as e:
        return {"success": False, "error": str(e)}

    if result.returncode != 0:
        # Ошибки компилятора возвращаются как есть: по ним человек (или сам
        # Scott на следующем шаге) поймёт, что именно не так с кодом.
        details = (result.stderr or result.stdout).strip()[:1500]
        if not details:
            details = (
                f"{compiler} завершился с кодом {result.returncode}, ничего не сообщив. "
                "Обычно так бывает, когда компилятору не хватает его собственного окружения."
            )
        return {"success": False, "compiled": False, "error": details}

    return {
        "success": True,
        "compiled": True,
        "binary": str(binary),
        "compiler": compiler,
        "warnings": result.stderr.strip()[:800],
    }


def run(path: str, language: str) -> Dict:
    """
    Запустить программу и вернуть то, что она напечатала.

    Таймаут обязателен: программа с бесконечным циклом иначе повесила бы Scott
    целиком, и человек не понял бы, почему ассистент перестал отвечать.
    """
    chain = TOOLCHAINS.get(language)
    if chain is None:
        return {"success": False, "error": f"Не знаю язык «{language}»"}

    target = Path(path)
    if not target.exists():
        return {"success": False, "error": f"Файл не найден: {path}"}

    if chain.compilers and language != "java":
        command = [str(target)]
    elif language == "java":
        command = ["java", target.stem]
    elif language == "csharp":
        command = ["dotnet", "run", "--project", str(target.parent)]
    else:
        interpreter = find_tool(chain.interpreters)
        if interpreter is None:
            return {"success": False, "error": f"Нечем запустить {chain.display}. {chain.install_hint}"}
        command = [interpreter, str(target)]

    try:
        result = subprocess.run(
            command, capture_output=True, text=True,
            timeout=RUN_TIMEOUT, cwd=str(target.parent),
            encoding="utf-8", errors="replace",
            # Собранная программа может зависеть от библиотек компилятора —
            # у MinGW это обычное дело, и без его каталога в PATH она не
            # запустится, хотя собралась.
            env=_tool_env(command[0]),
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"Программа не завершилась за {RUN_TIMEOUT} секунд — похоже на бесконечный цикл",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

    return {
        "success": result.returncode == 0,
        "output": result.stdout.strip(),
        "stderr": result.stderr.strip()[:1000],
        "exit_code": result.returncode,
    }


def manual_instructions(path: str, language: str) -> str:
    """
    Как запустить программу руками.

    Нужно, когда человек не хочет, чтобы Scott запускал что-то сам, — и когда
    компилятора нет: тогда это единственный способ довести дело до конца.
    """
    chain = TOOLCHAINS.get(language)
    if chain is None:
        return ""

    target = Path(path)
    folder = target.parent

    if language in ("c", "cpp"):
        compiler = chain.compilers[0]
        binary = target.with_suffix(".exe" if os.name == "nt" else "").name
        return (
            f"1. Откройте терминал в папке {folder}\n"
            f"2. Соберите: {compiler} {target.name} -o {binary}\n"
            f"3. Запустите: {'.\\' if os.name == 'nt' else './'}{binary}"
        )
    if language == "java":
        return (
            f"1. Откройте терминал в папке {folder}\n"
            f"2. Соберите: javac {target.name}\n"
            f"3. Запустите: java {target.stem}"
        )
    if language == "csharp":
        return f"1. Откройте терминал в папке {folder}\n2. Запустите: dotnet run"

    interpreter = chain.interpreters[0]
    return f"1. Откройте терминал в папке {folder}\n2. Запустите: {interpreter} {target.name}"
