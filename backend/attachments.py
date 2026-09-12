"""
Вложения: что Scott видит, когда ему дают файл.

ПОЧЕМУ ЭТОГО НЕ РАБОТАЛО. Кнопки прикрепления в лаунчере были, и файл даже
показывался в переписке, — но выбранное запоминалось одним лишь ИМЕНЕМ. Ни
путь, ни содержимое никуда не уходили, а вопрос отправлялся обычным запросом,
где вложения нет вовсе. Дело было не в модели: самая зоркая не увидит того,
чего ей не послали.

ДВЕ РАЗНЫЕ ДОРОГИ. Картинку нужно показать модели как картинку — закодировать
и передать вместе с вопросом; такое умеют не все модели, и честно сказать об
этом лучше, чем молча прислать ответ ни о чём. Документ, наоборот, незачем
показывать: из него извлекается текст, и дальше это обычный вопрос, на который
ответит любая модель.

ЧТО СЮДА НЕ ПОПАЛО. Распознавание текста на картинке. Скан договора выглядит
документом, а на деле это изображение, и текста в нём нет — для него нужен
отдельный движок, и тянуть его сюда ради редкого случая не стоит: зоркая
модель прочитает такой скан сама, глазами.
"""

from __future__ import annotations

import base64
import io
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from PIL import Image
except Exception:  # pragma: no cover — Pillow ставится вместе со Scott
    Image = None

try:
    import pypdf
except Exception:  # pragma: no cover
    pypdf = None

try:
    import docx as python_docx
except Exception:  # pragma: no cover
    python_docx = None


# Предел на размер вложения. Не защита от злого умысла: модели сами не примут
# больше, а человек, перетащивший фильм вместо снимка, должен получить внятный
# отказ, а не молчание на минуту.
MAX_BYTES = 20 * 1024 * 1024

# Наибольшая сторона картинки, которую отправляем модели.
#
# Снимок экрана с монитора в четыре тысячи точек весит мегабайты, а модель всё
# равно рассматривает его в уменьшенном виде. Полторы тысячи — предел, после
# которого мелкий текст на снимке ещё читается, а вес уже приемлем.
MAX_IMAGE_SIDE = 1568

# Сколько текста брать из документа.
#
# Ограничение не в знаках, а в здравом смысле: в запрос помещается лишь
# столько, сколько модель успеет прочитать, не потеряв вопрос. Договор на сто
# страниц придётся обсуждать по частям, и сказать об этом надо прямо.
MAX_TEXT_CHARS = 24_000

# Сколько страниц PDF разбирать. Столько же, сколько влезет по знакам, но
# считать страницы дешевле, чем разбирать сто и выбросить девяносто.
MAX_PDF_PAGES = 40

IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

# Текстовые форматы, которые читаются как есть. Код сюда входит намеренно:
# «посмотри, что не так в этом файле» — обычная просьба.
PLAIN_TYPES = {
    ".txt", ".md", ".csv", ".json", ".xml", ".yml", ".yaml", ".ini", ".log",
    ".py", ".js", ".ts", ".cs", ".java", ".go", ".rs", ".c", ".cpp", ".h",
    ".html", ".css", ".sql", ".sh", ".ps1", ".bat",
}


@dataclass
class Attachment:
    """
    Разобранное вложение.

    Либо картинка — тогда заполнены `image_base64` и `media_type`, либо текст —
    тогда заполнен `text`. Оба сразу не бывают: это две разные дороги.
    """

    name: str
    kind: str                      # 'image' | 'text' | 'refused'
    text: str = ""
    image_base64: str = ""
    media_type: str = ""
    note: str = ""                 # что человеку стоит знать: обрезка, отказ
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.kind in ("image", "text") and not self.error


def read(path: str | Path, data: Optional[bytes] = None) -> Attachment:
    """
    Разобрать вложение по пути или по уже прочитанным байтам.

    Байты передаются, когда файл пришёл по сети и на диске его нет. Имя при
    этом всё равно нужно: по расширению определяется, что с ним делать.
    """
    name = Path(path).name
    suffix = Path(path).suffix.lower()

    try:
        if data is None:
            file = Path(path)
            if not file.exists():
                return Attachment(name=name, kind="refused",
                                  error=f"Файл «{name}» не найден")
            data = file.read_bytes()

        if len(data) > MAX_BYTES:
            weight = len(data) / (1024 * 1024)
            return Attachment(
                name=name, kind="refused",
                error=f"Файл слишком большой: {weight:.0f} МБ, предел — "
                      f"{MAX_BYTES // (1024 * 1024)} МБ")

        if suffix in IMAGE_TYPES:
            return _read_image(name, data)

        if suffix == ".pdf":
            return _read_pdf(name, data)

        if suffix in (".docx", ".doc"):
            return _read_docx(name, data, suffix)

        if suffix in PLAIN_TYPES:
            return _read_plain(name, data)

        return Attachment(
            name=name, kind="refused",
            error=f"Не знаю, что делать с файлами «{suffix or 'без расширения'}». "
                  "Понимаю картинки, PDF, документы Word и текстовые файлы")
    except Exception as e:
        return Attachment(name=name, kind="refused", error=f"Не удалось прочитать: {e}")


def _read_image(name: str, data: bytes) -> Attachment:
    """
    Подготовить картинку к отправке модели.

    Крупные снимки уменьшаются: модель всё равно смотрит их в уменьшенном
    виде, а вес запроса растёт как площадь. Прозрачность сводится на белый —
    иначе при переводе в JPEG она станет чёрной, и светлый интерфейс на снимке
    экрана превратится в тёмное пятно.
    """
    media_type = mimetypes.guess_type(name)[0] or "image/png"
    note = ""

    if Image is not None:
        try:
            image = Image.open(io.BytesIO(data))
            side = max(image.size)

            if side > MAX_IMAGE_SIDE:
                ratio = MAX_IMAGE_SIDE / side
                new_size = (int(image.width * ratio), int(image.height * ratio))
                image = image.resize(new_size, Image.LANCZOS)

                if image.mode in ("RGBA", "LA", "P"):
                    flat = Image.new("RGB", image.size, (255, 255, 255))
                    flat.paste(image.convert("RGBA"), mask=image.convert("RGBA").split()[-1])
                    image = flat

                buffer = io.BytesIO()
                image.convert("RGB").save(buffer, format="JPEG", quality=85)
                data = buffer.getvalue()
                media_type = "image/jpeg"
                note = f"снимок уменьшен до {new_size[0]}×{new_size[1]}"
        except Exception:
            # Уменьшить не вышло — отправим как есть. Это хуже по весу, но
            # лучше, чем отказать из-за неудавшейся оптимизации.
            pass

    return Attachment(
        name=name,
        kind="image",
        image_base64=base64.b64encode(data).decode("ascii"),
        media_type=media_type,
        note=note,
    )


def _read_pdf(name: str, data: bytes) -> Attachment:
    if pypdf is None:
        return Attachment(name=name, kind="refused",
                          error="Чтение PDF недоступно: не установлена библиотека pypdf")

    reader = pypdf.PdfReader(io.BytesIO(data))
    pages = reader.pages[:MAX_PDF_PAGES]

    parts = []
    for number, page in enumerate(pages, start=1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception:
            text = ""

        if text:
            parts.append(f"[страница {number}]\n{text}")

    body = "\n\n".join(parts).strip()

    if not body:
        # Обычный случай: PDF собран из сканов, и текста в нём нет вовсе.
        return Attachment(
            name=name, kind="refused",
            error="В этом PDF нет текста — похоже, это отсканированные "
                  "изображения. Пришлите страницу картинкой: модель со зрением "
                  "прочитает её сама")

    note = ""
    if len(reader.pages) > MAX_PDF_PAGES:
        note = f"прочитаны первые {MAX_PDF_PAGES} страниц из {len(reader.pages)}"

    return _trim(Attachment(name=name, kind="text", text=body, note=note))


def _read_docx(name: str, data: bytes, suffix: str) -> Attachment:
    if suffix == ".doc":
        return Attachment(
            name=name, kind="refused",
            error="Старый формат .doc не читается. Пересохраните в .docx или PDF")

    if python_docx is None:
        return Attachment(name=name, kind="refused",
                          error="Чтение документов Word недоступно: "
                                "не установлена библиотека python-docx")

    document = python_docx.Document(io.BytesIO(data))
    parts = [p.text.strip() for p in document.paragraphs if p.text.strip()]

    # Таблицы идут отдельно: в договорах и отчётах самое важное часто именно в
    # них, а по абзацам они не проходят вовсе.
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))

    body = "\n".join(parts).strip()

    if not body:
        return Attachment(name=name, kind="refused",
                          error="Документ пуст или состоит из одних картинок")

    return _trim(Attachment(name=name, kind="text", text=body))


def _read_plain(name: str, data: bytes) -> Attachment:
    # Кодировку угадываем в два захода: сначала обычная для наших краёв UTF-8,
    # потом windows-1251, в которой до сих пор приходят старые текстовые файлы.
    for encoding in ("utf-8", "cp1251"):
        try:
            return _trim(Attachment(name=name, kind="text",
                                    text=data.decode(encoding).strip()))
        except UnicodeDecodeError:
            continue

    return Attachment(name=name, kind="refused",
                      error="Не удалось определить кодировку файла")


def _trim(attachment: Attachment) -> Attachment:
    """Обрезать слишком длинный текст и честно сказать об этом."""
    if len(attachment.text) <= MAX_TEXT_CHARS:
        return attachment

    attachment.text = attachment.text[:MAX_TEXT_CHARS]

    cut = f"взято первых {MAX_TEXT_CHARS // 1000} тысяч знаков"
    attachment.note = f"{attachment.note}, {cut}" if attachment.note else cut

    return attachment


def as_question(attachment: Attachment, question: str) -> str:
    """
    Собрать вопрос о документе.

    Текст документа идёт перед вопросом, а не после: так модель сначала читает
    материал и лишь затем узнаёт, что с ним делать, — и не начинает отвечать,
    не дочитав.
    """
    ask = question.strip() or "Прочитай документ и перескажи главное."

    return (
        f"Ниже содержимое файла «{attachment.name}».\n\n"
        f"---\n{attachment.text}\n---\n\n"
        f"{ask}"
    )
