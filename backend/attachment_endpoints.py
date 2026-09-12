"""
Вопрос о прикреплённом файле.

Файл приходит целиком в теле запроса, а не путём на диске. Так честнее: путь
имеет смысл только на той же машине, а лаунчер и backend, вообще говоря,
разные программы — сегодня рядом, завтра нет.

Дальше развилка, описанная в `attachments`: картинка уходит модели как
картинка, документ превращается в текст и становится обычным вопросом.
"""

from typing import Dict

from fastapi import APIRouter, File, Form, UploadFile

try:
    from . import attachments as attachments_module
except ImportError:
    import attachments as attachments_module

router = APIRouter(prefix="/attachments", tags=["attachments"])


def _answerer():
    """
    Отвечающий берётся при каждом запросе, а не сохраняется в модуле.

    Человек может переключить провайдера в настройках между двумя вопросами, и
    сохранённая ссылка указывала бы на прежнего — с прежним ключом и прежней
    моделью.
    """
    try:
        from .intelligent_answerer import intelligent_answerer
    except ImportError:
        from intelligent_answerer import intelligent_answerer

    return intelligent_answerer


@router.post("/ask")
async def ask_about_file(
    file: UploadFile = File(...),
    question: str = Form(""),
) -> Dict:
    """
    Разобрать файл и ответить на вопрос о нём.

    Без вопроса тоже можно: тогда Scott расскажет, что видит, — обычно этого и
    хотят, перетаскивая снимок экрана.
    """
    data = await file.read()
    name = file.filename or "файл"

    attachment = attachments_module.read(name, data=data)

    if not attachment.ok:
        return {
            "success": False,
            "error": attachment.error,
            "name": name,
        }

    answerer = _answerer()

    if attachment.kind == "image":
        answer, ok = answerer.answer_about_image(
            question, attachment.image_base64, attachment.media_type)
    else:
        # Документ — это обычный вопрос с материалом внутри. Отвечать на
        # него умеет любая модель, и отдельная дорога здесь была бы лишней.
        answer = answerer.answer_question(
            attachments_module.as_question(attachment, question))
        ok = bool(answer)

    return {
        "success": ok,
        "answer": answer,
        "name": name,
        "kind": attachment.kind,
        "note": attachment.note,
    }


@router.get("/ability")
async def vision_ability() -> Dict:
    """
    Умеет ли нынешняя модель смотреть картинки.

    Лаунчер спрашивает это до отправки: сказать заранее, что модель видит
    только текст, лучше, чем принять снимок и вернуть ответ ни о чём.
    """
    answerer = _answerer()

    return {
        "success": True,
        "provider": answerer.api_provider,
        "model": answerer.model,
        "sees_images": answerer.sees_images(),
        "reads_documents": bool(answerer.enabled),
    }
