"""Lost replies and process restarts cannot repeat an accepted request ID."""
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from backend.tests.test_chats import setup, create, routes
from backend.chat_store import ChatStore

pytestmark = pytest.mark.unit


def submit(env, chat, ident, text='fixture action', **changes):
    return env.client.post(f'/chats/{chat}/messages', data=dict(
        question=text, mode='command', request_id=ident, **changes))


def test_completed_request_survives_store_reopen_and_lost_http_response(setup, monkeypatch):
    actions=[]
    async def command(text, **kwargs):
        actions.append(text)
        return dict(response='Готово.')
    monkeypatch.setattr(routes, 'command_handler', command)
    original=routes._dispatch_message
    async def dropped(*args):
        await original(*args)
        raise ConnectionResetError('fixture response lost after commit')
    monkeypatch.setattr(routes, '_dispatch_message', dropped)
    chat, ident=create(setup), uuid.uuid4().hex
    with pytest.raises(ConnectionResetError):
        submit(setup, chat, ident)
    monkeypatch.setattr(routes, '_dispatch_message', original)
    monkeypatch.setattr(routes, 'store', lambda: ChatStore(setup.db.directory))
    monkeypatch.setattr(routes.request_receipts, 'OWNER', 'new-backend-process')
    status=setup.client.get(f'/chats/{chat}/requests/{ident}').json()
    assert status['request']['state']=='completed' and len(status['chat']['messages'])==2
    assert submit(setup, chat, ident).status_code==200
    assert actions==['fixture action'] and len(setup.db.get(chat)['messages'])==2


def test_concurrent_duplicate_never_enters_action_twice(setup, monkeypatch):
    entered, release=threading.Event(), threading.Event()
    actions=[]
    async def command(text, **kwargs):
        import asyncio
        actions.append(text); entered.set()
        assert await asyncio.to_thread(release.wait, 3)
        return dict(response='Готово.')
    monkeypatch.setattr(routes, 'command_handler', command)
    chat, ident=create(setup), uuid.uuid4().hex
    with ThreadPoolExecutor(1) as pool:
        first=pool.submit(submit, setup, chat, ident)
        try:
            assert entered.wait(1)
            assert submit(setup, chat, ident).status_code==409
            assert setup.client.get(f'/chats/{chat}/requests/{ident}').json()['request']['state']=='running'
        finally:
            release.set()
        assert first.result().status_code==200
    assert actions==['fixture action']


def test_failure_after_side_effect_preserves_draft_and_blocks_retry(setup, monkeypatch):
    actions=[]
    async def command(text, **kwargs):
        actions.append(text)
        raise RuntimeError('fixture failure after side effect')
    monkeypatch.setattr(routes, 'command_handler', command)
    chat, ident=create(setup), uuid.uuid4().hex
    with pytest.raises(RuntimeError):
        submit(setup, chat, ident)
    pending=setup.db.get(chat)['pending_request']
    assert pending==dict(id=ident,question='fixture action',state='uncertain')
    assert submit(setup, chat, ident).status_code==409 and actions==['fixture action']
    assert setup.db.get(chat)['messages']==[]


def test_restart_before_ack_is_uncertain_and_never_replayed(setup, monkeypatch):
    receipt=routes.request_receipts
    chat, ident=create(setup), uuid.uuid4().hex
    assert receipt.claim(setup.db, chat, ident, receipt.fingerprint('fixture action','command',[]), 'fixture action')
    monkeypatch.setattr(receipt, 'OWNER', 'replacement-backend')
    async def forbidden(*args,**kwargs):pytest.fail('Unconfirmed action repeated')
    monkeypatch.setattr(routes, 'command_handler', forbidden)
    assert submit(setup, chat, ident).status_code==409
    status=setup.client.get(f'/chats/{chat}/requests/{ident}').json()['request']
    assert status['state']=='uncertain' and status['question']=='fixture action'


def test_receipt_is_bound_to_body_and_chat(setup, monkeypatch):
    async def command(*args, **kwargs):return dict(response='Готово.')
    monkeypatch.setattr(routes, 'command_handler', command)
    chat, other, ident=create(setup), create(setup), uuid.uuid4().hex
    assert submit(setup, chat, ident).status_code==200
    assert submit(setup, chat, ident, text='different action').status_code==409
    assert submit(setup, other, ident).status_code==409
    assert setup.client.get(f'/chats/{other}/requests/{ident}').status_code==404


def test_clear_removes_text_but_keeps_nonreplayable_tombstone(setup, monkeypatch):
    actions=[]
    async def command(text, **kwargs):actions.append(text);return dict(response='Готово.')
    monkeypatch.setattr(routes, 'command_handler', command)
    chat, ident=create(setup), uuid.uuid4().hex
    assert submit(setup, chat, ident).status_code==200
    assert setup.client.delete(f'/chats/{chat}/messages').status_code==200
    assert setup.db.get(chat)['messages']==[] and 'pending_request' not in setup.db.get(chat)
    status=setup.client.get(f'/chats/{chat}/requests/{ident}').json()['request']
    assert status['state']=='cleared' and status['question']==''
    assert submit(setup, chat, ident).status_code==409 and len(actions)==1


@pytest.mark.parametrize('ident',['bad','f'*33,'../file','F'*32])
def test_invalid_receipt_fails_before_execution(setup, monkeypatch, ident):
    async def forbidden(*args,**kwargs):pytest.fail('Invalid receipt reached action')
    monkeypatch.setattr(routes, 'command_handler', forbidden)
    assert submit(setup, create(setup), ident).status_code==400


def test_model_turn_and_introduction_are_idempotent_too(setup):
    chat=create(setup)
    for text in ('Кто ты?', 'Explain fixture'):
        ident=uuid.uuid4().hex
        for _ in range(2):
            response=setup.client.post(f'/chats/{chat}/messages',data=dict(question=text,request_id=ident))
            assert response.status_code==200
    assert len(setup.db.get(chat)['messages'])==4 and len(setup.sent)==1


def test_model_failure_can_be_retried_without_repeating_actions(setup, monkeypatch):
    chat, ident=create(setup), uuid.uuid4().hex
    def broken(*args):raise RuntimeError('fixture provider offline')
    monkeypatch.setattr(routes, 'complete', broken)
    response=setup.client.post(f'/chats/{chat}/messages',data=dict(question='Explain fixture',request_id=ident))
    assert response.status_code==502
    assert setup.client.get(f'/chats/{chat}/requests/{ident}').json()['request']['state']=='failed'
    monkeypatch.setattr(routes, 'complete', lambda *args:'Recovered answer')
    response=setup.client.post(f'/chats/{chat}/messages',data=dict(question='Explain fixture',request_id=ident))
    assert response.status_code==200 and len(setup.db.get(chat)['messages'])==2


def test_invalid_input_can_be_corrected_without_poisoning_receipt(setup):
    chat, ident=create(setup), uuid.uuid4().hex
    assert submit(setup, chat, ident, text='').status_code==400
    assert setup.client.get(f'/chats/{chat}/requests/{ident}').json()['request']['state']=='failed'


def test_cleared_receipt_keeps_no_text_or_fingerprint(setup):
    receipt=routes.request_receipts
    chat, ident=create(setup), uuid.uuid4().hex
    receipt.claim(setup.db, chat, ident, receipt.fingerprint('private draft','chat',[]), 'private draft')
    setup.db.delete(chat,clear=True)
    with setup.db.connect() as db:
        row=db.execute('SELECT * FROM requests WHERE id=?',(ident,)).fetchone()
        assert row['question']==row['fingerprint']==row['owner']==row['phase']==''


def test_upgrade_preserves_existing_history_and_marks_old_pending_conservatively(setup):
    chat=create(setup)
    setup.db.commit_turn(chat,'Previous question','Previous question','Previous answer','fixture',[])
    ident=uuid.uuid4().hex
    with setup.db.connect() as db:
        db.execute('DROP TABLE requests')
        db.execute('''CREATE TABLE requests(id TEXT PRIMARY KEY, chat_id TEXT NOT NULL
            REFERENCES chats(id) ON DELETE CASCADE, fingerprint TEXT NOT NULL, question TEXT NOT NULL,
            state TEXT NOT NULL, owner TEXT NOT NULL)''')
        db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?)',
                   (ident,chat,'digest','Unfinished question','pending','old-process'))
    upgraded=ChatStore(setup.db.directory)
    saved=upgraded.get(chat)
    assert [row['text'] for row in saved['messages']]==['Previous question','Previous answer']
    assert saved['pending_request']==dict(id=ident,question='Unfinished question',state='uncertain')
    with upgraded.connect() as db:
        assert db.execute('SELECT phase FROM requests WHERE id=?',(ident,)).fetchone()['phase']=='effect'
