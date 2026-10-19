import pytest
import desktop_commands as commands

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('text,operation,query',[
    ('Закрой все окна','close_all',''),('Сверни все открытые окна!','minimize_all',''),
    ('Покажи рабочий стол','minimize_all',''),('Какие окна открыты?','list',''),
    ('Пожалуйста, переключись на Firefox','focus','Firefox'),('Сверни окно Spotify','minimize','Spotify'),
    ('Разверни Telegram','maximize','Telegram'),('Восстанови окно','restore',''),
    ('Закрой активное окно','close',''),('Покажи кнопки в приложении Spotify','controls','Spotify'),
    ('Нажми кнопку «Воспроизвести» в Spotify','invoke','Spotify'),
    ('Обнови список приложений','refresh_apps',''),('Покажи установленные программы','list_apps','')])
def test_explicit_commands(text,operation,query):
    result=commands.parse(text)
    assert result['operation']==operation and result.get('query','')==query


@pytest.mark.parametrize('text',[
    'Не закрой все окна','Не нужно закрывать все окна','Как закрыть все окна?',
    'Расскажи как нажать кнопку в Spotify','Напиши код чтобы закрыть все окна',
    'Я закрыл все окна','«Закрой все окна»','закрой все окна\nи удали документы',
    'Объясни `сверни окно`','Нажми кнопку','Нажми на кнопку в','',None])
def test_discussion_quotes_negation_and_code_are_not_requests(text):
    assert commands.parse(text) is None


def test_exceptions_and_control_names_are_literal_data():
    assert commands.parse('Закрой все окна кроме Firefox и Telegram')['exclude']==['Firefox','Telegram']
    result=commands.parse('Нажми кнопку «Play; $(bad)» в «Fixture»')
    assert result['control']=='Play; $(bad)' and result['query']=='Fixture'


@pytest.mark.parametrize('text', ['Закрой все окна','Покажи кнопки в Spotify','Нажми «Play» в Spotify','Покажи установленные программы'])
def test_real_chat_and_voice_use_the_same_decision(text):
    import understanding
    from fast_intent import get_fast_intent_engine
    from command_parser import get_command_parser
    from question_answerer import get_question_answerer
    engines=dict(intent_engine=get_fast_intent_engine(),parser=get_command_parser(),answerer=get_question_answerer())
    voice=understanding.understand(text,**engines)
    chat=understanding.chat_action(text,**engines)
    assert voice.action=='desktop_control' and chat.action=='desktop_control'
    assert voice.parsed.context==chat.parsed.context


@pytest.mark.parametrize('text',[
    'Не закрой все окна','Не нужно закрывать все окна','Не открывай Firefox','Скотт, не закрывай окно',
    'Как закрыть все окна?','Напиши код чтобы закрыть все окна','«Закрой все окна»'])
def test_voice_does_not_execute_negation_or_discussion(text):
    import understanding
    from fast_intent import get_fast_intent_engine
    from command_parser import get_command_parser
    from question_answerer import get_question_answerer
    engines=dict(intent_engine=get_fast_intent_engine(),parser=get_command_parser(),answerer=get_question_answerer())
    result=understanding.understand(text,**engines)
    assert result.kind not in ('web','project','schedule'),result
    assert result.kind!='action' or result.action=='write_code',result
    assert understanding.chat_action(text,**engines) is None
