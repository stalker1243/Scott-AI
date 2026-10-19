"""Local introduction and voice follow-ups must not contact a model."""
import pytest
from backend import assistant_identity as identity


@pytest.mark.parametrize('text', ['Кто ты?', 'Скотт, кто ты такой?', 'Ты кто?',
    'Привет, Скотт, расскажи о себе!', 'Представься, пожалуйста', 'Как тебя зовут?', 'Who are you?'])
def test_introduction(text):
    assert identity.reply(text) == identity.INTRODUCTION
    assert identity.OFFER in identity.reply(text)


@pytest.mark.parametrize('text', ['Кто твой создатель?', 'А кто тебя создал?',
    'Кто тебя разработал?', 'Как зовут твоего автора?', 'Кто такой Phantom?'])
def test_creator_uses_only_supplied_biography(text):
    answer = identity.reply(text)
    assert answer == identity.CREATOR
    assert answer.startswith('Мой создатель — Phantom. ')
    assert 'автоматизация' in answer and 'Scott Voice' in answer


@pytest.mark.parametrize('text', ['Кто автор приложения?', 'Назови настоящее имя автора',
                                'Расскажи про Phantom', 'Какое ФИО у разработчика?'])
def test_creator_context_uses_only_the_public_alias(text):
    context=identity.prompt_context(text)
    assert 'Создатель приложения — Phantom.' in context
    assert 'только Phantom' in context and 'не является публичной информацией' in context


def test_authorization_question_is_not_a_creator_question():
    assert identity.prompt_context('Как исправить авторизацию?') == ''


@pytest.mark.parametrize('text', ['Да', 'да, расскажи подробнее', 'Ага!', 'Конечно', 'Объясни, пожалуйста'])
def test_yes_requires_the_immediately_previous_offer(text):
    assert identity.reply(text) is None
    assert identity.reply(text, identity.INTRODUCTION) == identity.HOW_IT_WORKS
    assert identity.reply(text, identity.CREATOR) == identity.HOW_IT_WORKS
    assert identity.reply(text, identity.HOW_IT_WORKS) is None


@pytest.mark.parametrize('text', ['Кто твой создатель Python?', 'Кто ты по гороскопу?',
    'Переведи фразу кто ты', 'Да, открой Spotify', 'Как работает процессор?', 'Расскажи о себе на собеседовании'])
def test_unrelated_requests_are_not_swallowed(text):
    assert identity.reply(text, identity.INTRODUCTION) is None


def test_voice_decline_topic_change_and_timeout_end_the_offer():
    clock = [10.0]
    voice = identity.VoiceIntroduction(lambda: clock[0])
    assert voice.answer('кто ты') == identity.INTRODUCTION
    assert voice.answer('нет, спасибо') == identity.DECLINED
    assert voice.answer('да') is None
    voice.answer('кто тебя создал')
    voice.answer('сколько времени')
    assert voice.answer('да') is None
    voice.answer('кто ты')
    clock[0] += 181
    assert voice.answer('да') is None
    assert identity.VoiceIntroduction().answer('да') is None


def test_voice_explanation_is_consumed_once():
    voice = identity.VoiceIntroduction()
    voice.answer('Кто твой создатель?')
    assert voice.answer('да') == identity.HOW_IT_WORKS
    assert voice.answer('да') is None
    assert 'API Token' in identity.HOW_IT_WORKS and 'Demo' in identity.HOW_IT_WORKS


def test_voice_followup_probe_does_not_consume_or_extend_the_offer():
    clock = [10.0]
    voice = identity.VoiceIntroduction(lambda: clock[0])
    assert not voice.accepts_followup('да')
    voice.answer('кто ты')
    assert voice.accepts_followup('Да, расскажи подробнее')
    assert voice.accepts_followup('Нет, спасибо')
    assert not voice.accepts_followup('Да, открой Spotify')
    assert voice.answer('да') == identity.HOW_IT_WORKS
    assert not voice.accepts_followup('да')
    voice.answer('кто ты')
    clock[0] += 179
    assert voice.accepts_followup('да')
    clock[0] += 2
    assert not voice.accepts_followup('да')


def test_question_answerer_and_extended_answers_share_the_identity(monkeypatch):
    from backend.question_answerer import QuestionAnswerer
    from backend.extended_responses import try_extended_answer
    qa = QuestionAnswerer()
    monkeypatch.setattr(qa, '_ai_fallback', lambda *a, **k: pytest.fail('Model called'))
    assert qa.answer('Скотт, кто твой создатель?', brief=True) == identity.CREATOR
    assert try_extended_answer('Кто ты?') == identity.INTRODUCTION
    assert try_extended_answer('Кто ты по гороскопу?') is None
