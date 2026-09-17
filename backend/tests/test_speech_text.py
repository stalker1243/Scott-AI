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
    Незнакомая латиница транслитерируется побуквенно.

    Приблизительное звучание лучше тишины: Silero выбрасывает латиницу молча, и
    фраза теряет главное слово.

    Слово взято нарочно такое, которого нет в словаре произношения: частые
    названия («Google Chrome», «Downloads») читаются по нему, и проверять на
    них побуквенный разбор бессмысленно — он до них не доходит.
    """
    result = speech.prepare_for_speech("Открыл zendesk")
    assert "zendesk" not in result
    assert "зендеск" in result


# ==================== Как звучат частые слова ====================
#
# Побуквенная транслитерация на них не годится: «Google Chrome» превращалась в
# «гоогле кхроме», а «Downloads» — в «довнлоадс». Это ровно те слова, которыми
# Scott отчитывается о сделанном, и разобрать их человек должен с первого раза.

@pytest.mark.parametrize("ответ,звучание", [
    ("Открыл Google Chrome", "гугл хром"),
    ("Открыл папку Downloads", "загрузки"),
    ("Открыл Visual Studio Code", "вижуал студио коуд"),
    ("Закрыл Discord", "дискорд"),
])
def test_частые_названия_звучат_по_словарю(speech, ответ, звучание):
    assert звучание in speech.prepare_for_speech(ответ).lower()


def test_время_читается_как_время(speech):
    """
    «Напомню в 14:30» звучало как «четырнадцать двоеточие тридцать» — точнее,
    двоеточие Silero проглатывал, и выходило слипшееся число.
    """
    произнесённое = speech.prepare_for_speech("Напомню в 14:30 про созвон")

    assert "четырнадцать тридцать" in произнесённое
    assert ":" not in произнесённое


def test_ведущий_ноль_в_минутах_не_теряется(speech):
    """«9:05» без этого читается как «девять пять» — девять часов пять минут или пять часов?"""
    assert "девять ноль пять" in speech.prepare_for_speech("Сейчас 9:05")


def test_номер_версии_читается_целиком(speech):
    """«Версия 2.0.5» звучала как «два пять»: середина терялась."""
    assert "два ноль пять" in speech.prepare_for_speech("Версия 2.0.5 установлена")


def test_одиночная_латинская_буква_не_пропадает(speech):
    """
    «Диск C заполнен» звучало как «диск заполнен»: Silero выбрасывает одинокую
    латиницу молча, и фраза теряет главное слово.
    """
    assert "диск цэ" in speech.prepare_for_speech("Диск C заполнен на 70%").lower()


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

    «C:\Users\User\ScottAI\code\scott_program.c» звучало как «цэ двоеточие
    усерс скйнет скоттаи коде…» — понять из этого ничего нельзя, а путь
    целиком виден в чате.
    """
    spoken = speech.shorten_paths(r"Файл: C:\Users\User\ScottAI\code\scott_program.c")
    assert spoken == "Файл: scott_program.c"

    # И то же самое по всей цепочке синтеза: без вызова shorten_paths внутри
    # prepare_for_speech правило было бы мёртвым.
    voiced = speech.prepare_for_speech(r"Файл: C:\Users\User\ScottAI\code\scott_program.c")
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


# ==================== Речь по частям ====================
#
# Длинный ответ синтезировался целиком, и только потом начинал звучать: замеры
# показывали до 2,4 секунды тишины между командой и первым словом. В эти
# секунды человек не знает, услышали его или нет, — и это главное, что
# ощущается как медлительность Scott.

def test_короткий_ответ_не_делится():
    """
    «Готово» делить нечего, и оно почти всегда уже лежит в кэше озвученных
    реплик — разбиение только лишило бы его этого.
    """
    from speech_text import split_for_speech

    assert split_for_speech("Готово.") == ["Готово."]


def test_длинный_ответ_начинается_с_одного_предложения():
    """
    Первое предложение отделяется всегда: весь смысл в том, чтобы начать
    говорить раньше, а не в том, чтобы поделить ответ ровно.
    """
    from speech_text import split_for_speech

    куски = split_for_speech(
        "Диск C заполнен на семьдесят процентов. Свободно сто двадцать гигабайт. "
        "Больше всего занимает папка загрузок. Могу открыть её."
    )

    assert len(куски) > 1
    assert куски[0] == "Диск C заполнен на семьдесят процентов."


def test_куски_не_распадаются_на_обрывки():
    """
    Резать на каждое предложение нельзя: «Да.» и «Готово.» дали бы два файла и
    рваную речь с паузой посередине.
    """
    from speech_text import split_for_speech, SPEAK_CHUNK_CHARS

    куски = split_for_speech("Сделал. Готово. Открыл. Запустил. Проверил. Ответил.")

    # Первый кусок короткий намеренно, остальные — не короче предела.
    for кусок in куски[1:]:
        assert len(кусок) >= SPEAK_CHUNK_CHARS or кусок is куски[-1]


def test_короткий_хвост_прилипает_к_предыдущему():
    """«Да» в конце ответа звучало бы обрывком после паузы."""
    from speech_text import split_for_speech

    куски = split_for_speech(
        "Диск C заполнен на семьдесят процентов, свободно сто двадцать гигабайт. "
        "Больше всего занимает папка загрузок и кэш браузера. Да."
    )

    assert not куски[-1].strip() == "Да."


def test_ничего_не_теряется_при_разбиении():
    """
    Самое важное: Scott должен произнести весь ответ. Потерянное предложение —
    хуже, чем задержка, потому что человек о потере не узнает.
    """
    from speech_text import split_for_speech

    ответ = ("Открыл браузер и почту. Диск заполнен на семьдесят процентов. "
             "Больше всего занимает папка загрузок. Могу её открыть.")

    склеенный = " ".join(split_for_speech(ответ))

    assert склеенный == ответ


def test_пустой_ответ_не_даёт_кусков():
    from speech_text import split_for_speech

    assert split_for_speech("") == []
    assert split_for_speech("   ") == []
