import asyncio
from types import SimpleNamespace
import pytest

pytestmark=pytest.mark.unit


@pytest.mark.parametrize('failure',['cache','archive','both'])
def test_memory_failures_do_not_replace_successful_action(main_module,monkeypatch,failure):
    main=main_module
    from command_parser import ParsedCommand
    from understanding import Decision
    calls=[]
    def fail(*args,**kwargs):raise OSError('fixture disk failure')
    monkeypatch.setattr(main.memories_module,'observe',lambda _:[])
    monkeypatch.setattr(main,'HAS_V32_FEATURES',False)
    monkeypatch.setattr(main,'knowledge_base',SimpleNamespace(add_conversation=fail if failure in ('cache','both') else lambda *args:None))
    memory=SimpleNamespace(record_external_turn=fail if failure in ('archive','both') else lambda *args:None)
    monkeypatch.setattr(main,'intelligent_answerer',SimpleNamespace(memory=memory))
    async def execute(*args):calls.append(1);return 'fixture action completed'
    monkeypatch.setattr(main.scott_ai,'_execute_parsed_command',execute)
    decision=Decision(kind='action',action='open_app',parsed=ParsedCommand('open_app','fixture',{},1.))
    result=asyncio.run(main.scott_ai.process_command('открой fixture',decision=decision))
    assert result['response']=='fixture action completed' and calls==[1]
    if failure in ('archive','both'):assert result['memory_warning']


def test_desktop_errors_are_reported_without_learning_success(main_module,monkeypatch):
    main=main_module
    import desktop_control
    import understanding
    monkeypatch.setattr(main.memories_module,'observe',lambda _:[])
    monkeypatch.setattr(desktop_control,'execute',lambda _:dict(success=False,response='fixture unavailable'))
    decision=understanding.understand('Закрой все окна',**main.scott_ai._understanding_engines())
    result=asyncio.run(main.scott_ai.process_command('Закрой все окна',decision=decision))
    assert result['type']=='desktop_error' and not result['success']
    assert result['response']=='fixture unavailable'
