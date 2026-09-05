"""
Scott пишет программу по просьбе на человеческом языке.

Связывает три вещи, которые по отдельности уже есть: LLM, который умеет писать
код, знание о том, чем эта машина умеет собирать (`code_tools`), и голосовой
разбор просьбы.

Главная забота здесь — не сгенерировать текст, а довести дело до работающей
программы. Поэтому:

* язык проверяется ДО обращения к модели: писать на C, когда компилятора нет,
  значит потратить время человека и выдать файл, с которым он ничего не
  сделает;
* из ответа модели вынимается именно код, а не рассказ о нём — в файл должно
  попасть то, что компилируется;
* при ошибке сборки Scott показывает, что сказал компилятор, а не прячет это
  за «не получилось».
"""

from __future__ import annotations

import re
from typing import Dict, Optional

try:
    from . import code_tools
except ImportError:
    import code_tools

# Как просят написать программу. Требуется глагол — иначе под правило попадёт
# любой разговор о языках программирования.
CODE_REQUEST = re.compile(
    r"\b(напиши|написать|сделай|создай|сгенерируй|набросай)\b[^.]{0,60}?"
    r"\b(программ\w*|код|скрипт|функци\w*|класс|приложени\w*)\b",
    re.IGNORECASE,
)

# Просьба запустить то, что было написано.
RUN_REQUEST = re.compile(
    r"\b(запусти|запустить|выполни|проверь)\b.{0,30}\b(программ\w*|код|её|его|это)\b",
    re.IGNORECASE,
)

# Блок кода в ответе модели. Язык после тройных кавычек необязателен: модели
# пишут то «```c», то просто «```».
CODE_BLOCK = re.compile(r"```[a-zA-Z+#]*\s*\n(.*?)```", re.DOTALL)


def is_code_request(text: str) -> bool:
    return bool(CODE_REQUEST.search(text))


def is_run_request(text: str) -> bool:
    return bool(RUN_REQUEST.search(text))


def extract_code(answer: str) -> Optional[str]:
    """
    Достать код из ответа модели.

    Модель почти всегда обрамляет код тройными кавычками, но иногда добавляет
    вокруг объяснение — в файл должно попасть только то, что компилируется.
    Если разметки нет вовсе, но текст похож на программу, берём его целиком:
    лучше попробовать собрать, чем отказать из-за отсутствия кавычек.
    """
    blocks = CODE_BLOCK.findall(answer)
    if blocks:
        # Берём самый большой блок: короткие обычно показывают вывод программы
        # или команду запуска, а не саму программу.
        return max(blocks, key=len).strip()

    looks_like_code = any(
        marker in answer
        for marker in ("#include", "def ", "function ", "class ", "public static", "console.log", "print(")
    )
    return answer.strip() if looks_like_code else None


def build_prompt(request: str, language: str) -> str:
    """
    Просьба к модели.

    Требование про один блок кода не формальность: всё, что модель напишет
    вокруг, придётся отрезать, а ошибка отрезания превратится в несобираемый
    файл.
    """
    display = code_tools.TOOLCHAINS[language].display
    return (
        f"Напиши программу на {display}. Требование пользователя: {request}\n\n"
        "Ответь ОДНИМ блоком кода в тройных кавычках, без объяснений до и после. "
        "Программа должна компилироваться и запускаться как есть, без правок. "
        "Комментарии внутри кода — по-русски."
    )


def write_program(request: str, answerer, language: Optional[str] = None, name: str = "program") -> Dict:
    """
    Написать программу: выбрать язык, спросить модель, сохранить файл.

    Возвращает всё, что нужно показать человеку: код, путь, язык и — если
    язык не поддерживается этой машиной — подсказку, чего не хватает.
    """
    language = language or code_tools.detect_language(request)
    if language is None:
        return {
            "success": False,
            "message": "Не понял, на каком языке писать. Скажите, например, «на C» или «на питоне».",
        }

    info = code_tools.inspect(language)
    if not info["available"]:
        # Проверка до обращения к модели: иначе человек подождёт ответа, чтобы
        # узнать, что запустить его всё равно нечем.
        return {
            "success": False,
            "language": language,
            "message": (
                f"Написать на {info['display']} могу, но собрать нечем: "
                f"нужного инструмента нет. {info['install_hint']}"
            ),
            "install_hint": info["install_hint"],
        }

    if answerer is None:
        return {"success": False, "message": "Модель ИИ не настроена — писать код нечем"}

    try:
        answer, ok = answerer.answer(build_prompt(request, language), use_memory=False)
    except Exception as e:
        return {"success": False, "message": f"Модель не ответила: {e}"}

    if not ok or not answer:
        return {"success": False, "message": "Модель не смогла написать программу"}

    code = extract_code(answer)
    if not code:
        return {"success": False, "message": "В ответе модели не нашлось кода"}

    saved = code_tools.save_source(code, language, name)
    if not saved["success"]:
        return {"success": False, "message": saved["error"]}

    return {
        "success": True,
        "language": language,
        "display": info["display"],
        "code": code,
        "path": saved["path"],
        "instructions": code_tools.manual_instructions(saved["path"], language),
    }


def build_and_run(path: str, language: str, run_it: bool = True) -> Dict:
    """
    Собрать и, если просили, запустить.

    Запуск отделён от сборки намеренно: человек мог попросить только написать,
    и выполнять программу без его слова неправильно — она делает что угодно на
    его компьютере.
    """
    built = code_tools.build(path, language)
    if not built["success"]:
        return {
            "success": False,
            "stage": "build",
            "error": built.get("error", ""),
            "message": "Программа не собралась — вот что сказал компилятор",
        }

    if not run_it:
        return {
            "success": True,
            "stage": "build",
            "binary": built.get("binary"),
            "message": "Программа собрана. Скажите «запусти», когда будете готовы.",
        }

    target = built.get("binary") or path
    result = code_tools.run(target, language)

    return {
        "success": result["success"],
        "stage": "run",
        "output": result.get("output", ""),
        "error": result.get("error") or result.get("stderr", ""),
        "exit_code": result.get("exit_code"),
    }
