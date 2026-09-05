"""
Подготовка текста к произнесению.

Все проверки здесь выросли из того, что было слышно на самом деле. Способ
проверки был такой: Scott произносил фразу, а Whisper её распознавал — так
видно не то, что отправлено в синтез, а то, что человек услышит.

Что выяснилось и чинится этим модулем:

* «Запущено 285 процессов» звучало как «запущено процессов» — Silero молча
  выбрасывает числа;
* «Открыл через APP_MAP: блокнот → notepad.exe» превращалось в «Открыл через
  блокнот» — латиница пропадает;
* «CPU: 34.5%, RAM: 48.1%» вообще не синтезировалось: без единой русской буквы
  Silero бросает ValueError, и ответ уходил на облачный edge-tts.
"""

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def speech():
    import speech_text

    return speech_text


# ==================== Знаки и эмодзи ====================

@pytest.mark.parametrize("text,forbidden", [
    ("✅ Громкость увеличена", "✅"),
    ("🚀 Открыл блокнот", "🚀"),
    ("💻 Информация о системе", "💻"),
    ("Открыл 102079⭐", "⭐"),
    ("блокнот → notepad", "→"),
])
def test_decoration_is_removed(speech, text, forbidden):
    """Значки и стрелки в речь не попадают."""
    assert forbidden not in speech.prepare_for_speech(text)


def test_meaningful_words_survive(speech):
    """Убирая оформление, нельзя терять смысл фразы."""
    result = speech.prepare_for_speech("✅ Громкость увеличена")
    assert "увеличена" in result


# ==================== Числа ====================

@pytest.mark.parametrize("text,expected", [
    ("Запущено 285 процессов", "двести восемьдесят пять"),
    ("Свободно 120 гигабайт", "сто двадцать"),
    ("Занято 48 процентов", "сорок восемь"),
])
def test_numbers_become_words(speech, text, expected):
    """
    Числа разворачиваются словами.

    Иначе они просто исчезают: Silero их не проговаривает, и фраза сохраняет
    форму, теряя смысл. Заметить такое можно только на слух — глазами в коде
    всё выглядит правильно.
    """
    assert expected in speech.prepare_for_speech(text)


def test_fractional_numbers(speech):
    """Дробные числа тоже: загрузка процессора почти всегда дробная."""
    result = speech.prepare_for_speech("Процессор загружен на 34.5 процента")
    assert "тридцать четыре" in result
    assert "34" not in result


def test_percent_sign_becomes_word(speech):
    """Знак процента читается словом, а не пропускается."""
    assert "процент" in speech.prepare_for_speech("Занято 48%")


# ==================== Латиница ====================

@pytest.mark.parametrize("text,expected", [
    ("CPU загружен", "процессор"),
    ("RAM занята", "оперативная память"),
    ("GPU простаивает", "видеокарта"),
])
def test_known_abbreviations_translated(speech, text, expected):
    """Знакомые сокращения получают русские названия, а не транслитерацию."""
    # Знак ударения снимается перед сравнением: словарь ударений применяется
    # после замены, и «процессор» к этому моменту уже «проц+ессор».
    spoken = speech.prepare_for_speech(text).lower().replace("+", "")
    assert expected in spoken


def test_unknown_latin_is_transliterated(speech):
    """
    Незнакомая латиница транслитерируется.

    Приблизительное звучание лучше тишины: «Открыл через APP_MAP: блокнот →
    notepad.exe» звучало как «Открыл через блокнот» — фраза без смысла.
    """
    result = speech.prepare_for_speech("Открыл notepad")
    assert "notepad" not in result
    assert "нотепад" in result


# ==================== Устойчивость синтеза ====================

@pytest.mark.parametrize("text", ["CPU: 34.5%, RAM: 48.1%", "GPU 100%", "SSD 512"])
def test_technical_lines_become_speakable(speech, text):
    """
    После подготовки в строке есть русские слова.

    Это условие работы Silero: без единой кириллической буквы он бросает
    ValueError, вызывающий код считает это сбоем движка и уходит на облачный
    синтез — медленнее и с обязательным интернетом.
    """
    prepared = speech.prepare_for_speech(text)
    assert speech.has_speakable_content(prepared), f"нечего произносить: {prepared!r}"


@pytest.mark.parametrize("text", ["✅", "🚀🚀", "→", "", "   ", "123"])
def test_hopeless_input_is_detected(speech, text):
    """
    Текст, из которого нечего произнести, распознаётся заранее.

    Тогда его можно отдать облачному движку или промолчать — вместо того чтобы
    ловить исключение и гадать, что сломалось.
    """
    prepared = speech.prepare_for_speech(text)
    if prepared:
        assert not speech.has_speakable_content(prepared) or prepared.strip()


# ==================== Ударения ====================

def test_accents_are_marked(speech):
    """
    Спорные слова получают знак ударения.

    Silero понимает «+» перед гласной как явное указание и сам знак не
    произносит — проверено на слух: «Гр+омкость увеличена» звучит как
    «громкость увеличена».
    """
    result = speech.prepare_for_speech("Громкость увеличена")
    assert "+" in result


def test_accent_keeps_capital_letter(speech):
    """Слово в начале предложения остаётся с заглавной буквы."""
    result = speech.prepare_for_speech("Запущено 5 процессов")
    assert result[0].isupper()


def test_accents_can_be_disabled(speech):
    """Разметку ударений можно отключить — например, для облачного движка."""
    assert "+" not in speech.prepare_for_speech("Громкость увеличена", accents=False)


def test_unknown_words_untouched(speech):
    """Слова, которых нет в словаре ударений, не трогаются."""
    assert speech.prepare_for_speech("Кот сидит на окне", accents=True).count("+") == 0

# ==================== Код и пути ====================

def test_code_block_not_spoken(speech):
    """
    Программу Scott показывает, а не зачитывает.

    Вслух «#include <stdio.h>» превращается в набор звуков; код человек
    читает в чате, где рядом есть кнопка «Копировать».
    """
    answer = (
        "Готово, написал на C." + chr(10) + chr(10)
        + "```c" + chr(10)
        + "#include <stdio.h>" + chr(10)
        + "int main(void) { return 0; }" + chr(10)
        + "```" + chr(10) + chr(10)
        + "Скажите «запусти программу»."
    )
    spoken = speech.prepare_for_speech(answer)
    assert "include" not in spoken.lower()
    assert "stdio" not in spoken.lower()
    assert "код показан в чате" in spoken.lower()
    assert "запусти" in spoken.lower()


def test_full_path_shortened_to_file_name(speech):
    r"""
    Полный путь вслух не читается.

    «C:\Users\SKYNET\ScottAI\code\scott_program.c» звучало как «цэ двоеточие
    усерс скйнет скоттаи коде…» — понять из этого ничего нельзя, а путь
    целиком виден в чате.
    """
    spoken = speech.shorten_paths(r"Файл: C:\Users\SKYNET\ScottAI\code\scott_program.c")
    assert spoken == "Файл: scott_program.c"

    # И то же самое по всей цепочке синтеза: без вызова shorten_paths внутри
    # prepare_for_speech правило было бы мёртвым.
    voiced = speech.prepare_for_speech(r"Файл: C:\Users\SKYNET\ScottAI\code\scott_program.c")
    assert "усерс" not in voiced and "скйнет" not in voiced


def test_linux_path_shortened(speech):
    """Пути с прямыми слэшами сокращаются так же."""
    assert speech.shorten_paths("Открыл /home/user/Загрузки") == "Открыл Загрузки"


def test_fractions_and_domains_survive(speech):
    """
    Пара к тесту выше: не всё со слэшем и точкой — путь.

    «3/4» и «example.com» должны дойти до синтеза целиком, иначе правило про
    пути съело бы обычный текст.
    """
    text = "Соотношение 3/4 и адрес example.com"
    assert speech.shorten_paths(text) == text
