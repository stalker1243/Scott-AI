"""
Вложения: картинки и документы.

Замечание с живого просмотра: Scott не разбирает прикреплённый файл, и был
вопрос — дело в модели или в чём-то ещё. Оказалось, что не в модели вовсе:
прикрепление в лаунчере запоминало одно лишь ИМЯ файла, а вопрос уходил
обычным запросом, где вложения нет. Самая зоркая модель не увидит того, чего
ей не послали.

Здесь проверяется разбор: что из файла достаётся, что честно отвергается и
как об этом сообщается. Сеть не трогается ни разу — модель подделывается.
"""

import base64
import io

import pytest

pytestmark = pytest.mark.unit


try:
    import attachments
except ImportError:  # pragma: no cover — запуск из корня репозитория
    from backend import attachments


def картинка(width=40, height=30, mode="RGB"):
    """Настоящий PNG нужного размера."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new(mode, (width, height), (120, 180, 240)).save(buffer, format="PNG")
    return buffer.getvalue()


# ==================== Текстовые файлы ====================

def test_plain_text_is_read():
    a = attachments.read("заметка.txt", data="Привет, это документ.".encode("utf-8"))

    assert a.ok
    assert a.kind == "text"
    assert "документ" in a.text


def test_old_encoding_is_read():
    """
    Старые текстовые файлы приходят в windows-1251.

    Отвергать их из-за кодировки значило бы отказывать в чтении половине
    архивов, которые у человека и лежат на диске.
    """
    a = attachments.read("старое.txt", data="Привет из прошлого".encode("cp1251"))

    assert a.ok
    assert "прошлого" in a.text


def test_code_file_is_read_as_text():
    """
    Код читается как текст: «посмотри, что не так в этом файле» — обычная
    просьба, и отвергать её из-за расширения незачем.
    """
    a = attachments.read("main.py", data=b"def hello():\n    return 1\n")

    assert a.ok
    assert "def hello" in a.text


def test_long_text_is_trimmed_and_says_so():
    """
    Слишком длинный документ обрезается, и человеку об этом сообщается.

    Молча обрезать нельзя: ответ будет о первой трети договора, а человек
    решит, что он обо всём.
    """
    длинный = ("строка документа " * 4000).encode("utf-8")
    a = attachments.read("договор.txt", data=длинный)

    assert a.ok
    assert len(a.text) <= attachments.MAX_TEXT_CHARS
    assert "знак" in a.note


# ==================== Картинки ====================

def test_image_becomes_base64():
    a = attachments.read("снимок.png", data=картинка())

    assert a.ok
    assert a.kind == "image"
    assert a.image_base64
    assert a.media_type.startswith("image/")

    # То, что закодировано, должно раскодироваться обратно в тот же файл.
    assert base64.b64decode(a.image_base64)


def test_large_image_is_shrunk():
    """
    Крупные снимки уменьшаются.

    Снимок экрана с большого монитора модель всё равно смотрит в уменьшенном
    виде: вес запроса растёт как площадь, польза — нет.

    Проверяется размер в точках, а не вес файла. Вес зависит от того, что на
    картинке: первая версия проверки сравнивала байты и упала на одноцветном
    образце — PNG сжимает сплошную заливку лучше, чем JPEG, и уменьшенная
    вышла тяжелее исходной. На настоящем снимке всё наоборот, но проверка не
    должна зависеть от удачного выбора образца.
    """
    from PIL import Image

    a = attachments.read("экран.png", data=картинка(3000, 2000))

    assert a.ok

    полученная = Image.open(io.BytesIO(base64.b64decode(a.image_base64)))

    assert max(полученная.size) <= attachments.MAX_IMAGE_SIDE
    assert "уменьшен" in a.note


def test_small_image_is_left_alone():
    """Мелкую картинку трогать незачем — уменьшать в ней нечего."""
    a = attachments.read("значок.png", data=картинка(40, 30))

    assert a.ok
    assert a.note == ""


def test_transparent_image_does_not_go_black():
    """
    Прозрачность сводится на белый, а не на чёрный.

    Иначе светлый интерфейс на снимке экрана превращается в тёмное пятно —
    ровно там, где человек и просит что-то разглядеть.
    """
    from PIL import Image

    a = attachments.read("прозрачный.png", data=картинка(3000, 2000, mode="RGBA"))
    assert a.ok

    полученная = Image.open(io.BytesIO(base64.b64decode(a.image_base64)))
    цвет = полученная.convert("RGB").getpixel((5, 5))

    assert sum(цвет) > 200, f"картинка почернела: {цвет}"


# ==================== Отказы ====================

def test_huge_file_is_refused_with_reason():
    """
    Слишком большой файл отвергается сразу и с понятной причиной.

    Человек, перетащивший фильм вместо снимка, должен узнать об этом сразу, а
    не через минуту молчания.
    """
    a = attachments.read("фильм.png", data=b"x" * (attachments.MAX_BYTES + 1))

    assert not a.ok
    assert "МБ" in a.error


def test_unknown_type_is_refused_and_lists_what_works():
    """Отказ должен говорить, что делать дальше, а не только «нельзя»."""
    a = attachments.read("архив.rar", data=b"x")

    assert not a.ok
    assert "PDF" in a.error


def test_missing_file_is_refused():
    a = attachments.read("нет-такого-файла.txt")

    assert not a.ok
    assert "не найден" in a.error


def test_old_word_format_suggests_a_way_out():
    a = attachments.read("отчёт.doc", data=b"x")

    assert not a.ok
    assert "docx" in a.error


# ==================== Вопрос о документе ====================

def test_document_goes_before_the_question():
    """
    Материал идёт перед вопросом.

    Так модель сначала читает документ и лишь затем узнаёт, что с ним делать,
    — и не начинает отвечать, не дочитав.
    """
    a = attachments.read("отчёт.txt", data="Выручка выросла вдвое.".encode("utf-8"))
    запрос = attachments.as_question(a, "Что случилось с выручкой?")

    assert запрос.index("Выручка выросла") < запрос.index("Что случилось")
    assert "отчёт.txt" in запрос


def test_question_may_be_empty():
    """
    Без вопроса тоже можно.

    Перетаскивая файл молча, человек обычно хочет услышать, что там вообще.
    """
    a = attachments.read("отчёт.txt", data="Текст".encode("utf-8"))
    запрос = attachments.as_question(a, "")

    assert "перескажи" in запрос.lower()


# ==================== Кто умеет смотреть ====================

def test_text_only_providers_are_known():
    """
    Groq и DeepSeek работают только с текстом.

    Сказать об этом заранее лучше, чем отправить снимок и вернуть ответ ни о
    чём: человек решит, что Scott не понял картинку, хотя тот её не получал.
    """
    try:
        import intelligent_answerer as ia
    except ImportError:  # pragma: no cover
        from backend import intelligent_answerer as ia

    assert ia.provider_sees_images("Anthropic")
    assert ia.provider_sees_images("OpenAI")
    assert ia.provider_sees_images("OpenRouter")

    assert not ia.provider_sees_images("Groq")
    assert not ia.provider_sees_images("DeepSeek")
    assert not ia.provider_sees_images("")
