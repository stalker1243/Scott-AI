"""Scott's own introduction, without an API call or a shared chat follow-up."""
import re
import threading
import time

OFFER = 'Хотите узнать, как я работаю?'
INTRODUCTION = (
    'Я ИИ-ассистент Скотт. Помогаю находить информацию, разбираться в сложных вопросах '
    'и автоматизировать повседневные задачи на компьютере. Со мной можно общаться '
    'текстом и голосом. ' + OFFER
)
CREATOR = (
    'Мой создатель — Phantom. '
    'Сначала он создавал меня как личного помощника, а затем решил развивать '
    'Скотта для всех пользователей. Главная идея проекта — автоматизация: '
    'помогать людям тратить меньше времени на рутинные задачи. Отдельное внимание '
    'он уделяет качеству речи, понятному произношению и особому голосу Scott Voice. ' + OFFER
)
HOW_IT_WORKS = (
    'Сначала я получаю ваше сообщение или распознаю голос. Простые команды '
    'и знакомство со мной обрабатываются в приложении. Для развёрнутых ответов '
    'я обращаюсь к выбранной вами ИИ-модели через API. API Token — это ключ '
    'доступа к сервису модели; его можно указать в настройках. '
    'В нынешней Demo-версии такое подключение служит основой ответов: '
    'собственной обученной языковой модели у проекта пока нет. '
    'При обращении к внешнему сервису ему передаются вопрос и нужный контекст. '
    'Распознавание речи и локальные голоса могут работать на компьютере; '
    'дополнительные возможности зависят от выбранной модели и установленных компонентов.'
)
DECLINED = 'Хорошо. Если захотите узнать подробнее, спросите: «Как ты работаешь?».'
MODEL_CONTEXT = (
    'Ты ИИ-ассистент Скотт. Создатель приложения — Phantom. '
    'Проект начался с личной автоматизации и развивается для всех пользователей. '
    'В Demo ответы даёт подключённая через API модель; собственной обученной '
    'языковой модели у ScottAI пока нет. Не придумывай биографию создателя '
    'и не выдавай желаемое качество Scott Voice за уже проверенный результат. '
    'Называй создателя только Phantom: его настоящее имя не является публичной информацией.'
)

_PREFIX = {'скотт', 'скот', 'scott', 'слушай', 'слушайте', 'скажи', 'скажите',
           'привет', 'здравствуй', 'здравствуйте', 'а', 'ну', 'пожалуйста'}
_SUFFIX = {'скотт', 'скот', 'scott', 'пожалуйста'}
_SELF = (
    r'(?:кто ты(?: такой)?|ты кто|как тебя зовут|представься|расскажи о себе|расскажи про себя)',
    r'кто такой (?:скотт|скот|scott|scottai)',
    r'(?:who are you|what is your name|introduce yourself)',
)
_CREATOR = (
    r'кто (?:твой (?:создатель|автор|разработчик)|тебя (?:создал|написал|разработал))',
    r'как зовут твоего (?:создателя|автора|разработчика)',
    r'расскажи (?:о своем|про своего) (?:создателе|создателя|авторе|автора|разработчике|разработчика)',
    r'кто такой (?:phantom|фантом)',
    r'расскажи (?:о|про) (?:phantom|фантома)',
)
_HOW = (
    r'как ты (?:работаешь|устроен)',
    r'(?:расскажи|объясни) (?:как ты (?:работаешь|устроен)|принцип (?:своей|твоей) работы)',
    r'как работает (?:скотт|scott|scottai)',
)
_YES = r'(?:(?:да|ага|конечно|хорошо|давай)(?: (?:расскажи|объясни)(?: подробнее)?)?|(?:расскажи|объясни)(?: подробнее)?)'
_NO = r'(?:нет(?: спасибо)?|не надо|не сейчас|позже|да не надо)'


def normalize(text):
    words = re.findall(r'[\w]+', text.casefold().replace('ё', 'е'))
    while words and words[0] in _PREFIX:
        words.pop(0)
    while words and words[-1] in _SUFFIX:
        words.pop()
    return ' '.join(words)


def reply(text, previous_assistant=None):
    """Only whole requests match; an offer must be the last assistant turn."""
    value = normalize(text)
    if any(re.fullmatch(pattern, value) for pattern in _SELF):
        return INTRODUCTION
    if any(re.fullmatch(pattern, value) for pattern in _CREATOR):
        return CREATOR
    if any(re.fullmatch(pattern, value) for pattern in _HOW):
        return HOW_IT_WORKS
    if previous_assistant in (INTRODUCTION, CREATOR):
        if re.fullmatch(_YES, value):
            return HOW_IT_WORKS
        if re.fullmatch(_NO, value):
            return DECLINED
    return None


def prompt_context(query):
    if re.search(r'создател|разработчик|\bавтор(?:а|е|у|ом|ы|ов)?\b|настоящ\w* (?:имя|фамили)|\bфио\b|phantom|фантом|скотт|\bscott(?:ai)?\b|как ты работаешь|собственн\w* модел', query.casefold()):
        return MODEL_CONTEXT
    return ''


class VoiceIntroduction:
    """One voice conversation; unrelated turns or three minutes end the offer."""
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._previous = None
        self._deadline = 0
        self._lock = threading.Lock()

    def accepts_followup(self, text):
        """Recognize a reply to an active offer without consuming it."""
        with self._lock:
            return (self._clock() < self._deadline
                    and self._previous in (INTRODUCTION, CREATOR)
                    and re.fullmatch(f'(?:{_YES}|{_NO})', normalize(text)) is not None)

    def answer(self, text):
        with self._lock:
            now = self._clock()
            previous = self._previous if now < self._deadline else None
            result = reply(text, previous)
            self._previous = result
            self._deadline = now + 180 if result in (INTRODUCTION, CREATOR) else 0
            return result
