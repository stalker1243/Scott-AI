"""Slow model calls must not lock history, duplicate turns or exhaust health workers."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from backend.tests.test_chats import setup, create, routes
from backend.bounded_work import WorkPool

pytestmark=pytest.mark.unit


@pytest.mark.parametrize('failure',[False,True])
def test_slow_command_archive_does_not_lock_history_or_repeat_action(setup,monkeypatch,failure):
    started=threading.Event();release=threading.Event();actions=[]
    async def command(text,**kwargs):actions.append(text);return dict(response='fixture done')
    def remember(*args):
        started.set()
        if failure:raise OSError('fixture archive failure')
        release.wait(3)
    monkeypatch.setattr(routes,'command_handler',command)
    monkeypatch.setattr(routes,'remember',remember)
    pool=WorkPool(1,'fixture-command-memory')
    actual_run=pool.run
    async def short(*args,**kwargs):
        kwargs['timeout']=.2
        return await actual_run(*args,**kwargs)
    monkeypatch.setattr(pool,'run',short)
    monkeypatch.setattr(routes.bounded_work,'memory',pool)
    chat=create(setup)
    try:
        with ThreadPoolExecutor(1) as executor:
            pending=executor.submit(setup.client.post,f'/chats/{chat}/messages',data={'mode':'command','question':'fixture action'})
            try:
                assert started.wait(1)
                begin=time.monotonic()
                assert setup.client.get(f'/chats/{chat}').status_code==200
                assert time.monotonic()-begin<.5
                result=pending.result(1)
                assert result.status_code==200 and result.json()['notes']
                assert len(setup.db.get(chat)['messages'])==2 and actions==['fixture action']
            finally:release.set()
    finally:pool.close()


def test_slow_model_does_not_block_history_and_other_chats(setup,monkeypatch):
    started=threading.Event();release=threading.Event();lock=threading.RLock()
    def complete(*args): started.set();release.wait(3);return 'fixture answer'
    monkeypatch.setattr(routes,'complete',complete)
    setup.ia._state_lock=lambda:lock
    chat=create(setup);other=create(setup)
    with ThreadPoolExecutor(1) as executor:
        pending=executor.submit(setup.client.post,f'/chats/{chat}/messages',data={'question':'fixture'})
        try:
            assert started.wait(1)
            begin=time.monotonic()
            assert setup.client.get('/chats').status_code==200
            assert setup.client.get(f'/chats/{chat}').status_code==200
            assert setup.client.patch(f'/chats/{other}',json={'title':'renamed'}).status_code==200
            assert setup.client.delete(f'/chats/{other}').status_code==200
            assert setup.client.get('/health').status_code==200
            assert time.monotonic()-begin<.5
            assert setup.client.post(f'/chats/{chat}/messages',data={'question':'duplicate'}).status_code==409
        finally: release.set()
        assert pending.result(2).status_code==200
    assert len(setup.db.get(chat)['messages'])==2


def test_timeout_retains_chat_reservation_and_never_commits_late_reply(setup,monkeypatch):
    class FastPool(WorkPool):
        force_short_timeout=True
        async def run(self,*args,**kwargs):
            if self.force_short_timeout:
                kwargs['timeout']=.06
            return await super().run(*args,**kwargs)
    pool=FastPool(1,'fixture-chat-timeout');release=threading.Event();started=threading.Event()
    monkeypatch.setattr(routes.bounded_work,'models',pool)
    def complete(*args):started.set();release.wait(3);return 'late fixture answer'
    monkeypatch.setattr(routes,'complete',complete)
    chat=create(setup);other=create(setup)
    try:
        assert setup.client.post(f'/chats/{chat}/messages',data={'question':'fixture'}).status_code==504
        assert started.is_set()
        assert setup.client.get(f'/chats/{chat}').status_code==200
        assert setup.client.post(f'/chats/{chat}/messages',data={'question':'duplicate'}).status_code==409
        assert setup.client.post(f'/chats/{other}/messages',data={'question':'overflow'}).status_code==503
        assert other not in routes._busy_chats
        assert setup.db.get(chat)['messages']==[]
    finally: release.set()
    deadline=time.monotonic()+2
    while chat in routes._busy_chats and time.monotonic()<deadline:time.sleep(.005)
    assert chat not in routes._busy_chats
    assert setup.db.get(chat)['messages']==[]
    # The timeout/late-reply assertions above retain the 60 ms budget. Recovery
    # uses the route's normal deadline, on the SAME pool after its slot is freed.
    pool.force_short_timeout=False
    def fresh(*args):
        # A recovered provider may take longer than the synthetic 60 ms timeout.
        time.sleep(.09)
        return 'fresh answer'
    monkeypatch.setattr(routes,'complete',fresh)
    try:
        assert setup.client.post(f'/chats/{chat}/messages',data={'question':'fresh'}).status_code==200
        assert len(setup.db.get(chat)['messages'])==2
        assert setup.db.get(chat)['messages'][-1]['text']=='fresh answer'
    finally:pool.close()


def test_cancelled_worker_checks_flag_before_contacting_provider(setup,monkeypatch):
    flag=threading.Event();flag.set()
    monkeypatch.setattr(routes,'complete',lambda *args:pytest.fail('Cancelled request reached provider'))
    with pytest.raises(Exception) as error:
        routes.send(create(setup),'fixture','chat',[],reserved=True,cancelled=flag)
    assert getattr(error.value,'status_code',None)==504
