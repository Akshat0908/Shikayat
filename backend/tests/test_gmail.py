from types import SimpleNamespace
from backend.app.mail.gmail import folders,search,raw_query

class Box:
    def __init__(self):
        self.selected=[]
        self.folder=SimpleNamespace(list=lambda:[SimpleNamespace(name='Alle Nachrichten',flags=('\\All',)),SimpleNamespace(name='Unerwünscht',flags=('\\Junk',))],set=self.set)
    def set(self,name,readonly=False):
        assert readonly
        self.selected.append(name)
    def fetch(self,criteria,**kwargs):
        assert kwargs['mark_seen'] is False
        return iter([SimpleNamespace(obj={'Message-ID':'<same>'})])

def test_localized_and_deduplicated():
    box=Box()
    assert folders(box)==['Alle Nachrichten','Unerwünscht']
    assert len(list(search(box,raw_query(message_id='<abc>',subject='demo'))))==1
    assert box.selected==['Alle Nachrichten','Unerwünscht']
    assert 'rfc822msgid:abc' in raw_query(message_id='<abc>')

def test_retry_reconnects_and_is_bounded(monkeypatch):
    import asyncio
    from backend.app.workers import retry_imap
    attempts=[]
    def flaky():
        attempts.append(1)
        if len(attempts)<3: raise TimeoutError('temporary')
        return 'ok'
    async def fast_sleep(_): pass
    monkeypatch.setattr(asyncio,'sleep',fast_sleep)
    assert asyncio.run(retry_imap(flaky))=='ok'
    assert len(attempts)==3
