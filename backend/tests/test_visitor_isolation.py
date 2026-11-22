import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi.testclient import TestClient
from starlette.requests import Request
from sqlmodel import Session, select
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import Case, Evidence, Event, Message
from backend.app.privacy import COOKIE, delete_expired, event_visible


def test_visitors_cannot_access_other_cases_or_events(tmp_path, monkeypatch):
    monkeypatch.setattr('backend.app.privacy.ROOT', tmp_path)
    app = create_app(Settings(database_url=f'sqlite:///{tmp_path}/db', admin_passcode='secret'))
    with TestClient(app, base_url='https://testserver') as client:
        response = client.get('/api/session')
        cookie_header = response.headers['set-cookie'].lower()
        assert 'httponly' in cookie_header and 'secure' in cookie_header and 'samesite=lax' in cookie_header
        a = client.cookies.get(COOKIE)
        client.cookies.clear()
        client.get('/api/session')
        b = client.cookies.get(COOKIE)
        assert a != b
        folder = tmp_path / 'var' / 'evidence' / str(uuid4())
        folder.mkdir(parents=True)
        evidence_path = folder / 'image.png'
        evidence_path.write_bytes(b'private image')
        with Session(app.state.engine) as db:
            acase = Case(title='A', owner_id=a)
            bcase = Case(title='B', owner_id=b)
            owner = Case(title='Owner', owner_id='owner')
            sandbox = Case(title='Sandbox', owner_id=b, facts_json={'demo_sample': True})
            db.add_all([acase, bcase, owner, sandbox]); db.commit()
            ids = [c.id for c in (acase, bcase, owner, sandbox)]
            evidence = Evidence(case_id=bcase.id, kind='screenshot', path=str(evidence_path))
            db.add(evidence); db.commit(); eid = evidence.id
        ac, bc, oc, sc = ids
        headers = {'cookie': f'{COOKIE}={a}'}
        assert [case['id'] for case in client.get('/api/cases', headers=headers).json()] == [ac]
        for cid in (bc, oc, sc):
            for method, path in [('get', ''), ('get', '/board'), ('get', '/evidence'), ('post', '/pause'), ('delete', '')]:
                assert getattr(client, method)(f'/api/cases/{cid}{path}', headers=headers).status_code == 404
        assert client.get(f'/api/cases/{bc}/evidence/{eid}/file', headers=headers).status_code == 404
        assert client.get('/var/evidence/'+folder.name+'/image.png', headers=headers).status_code == 404
        scope = {'type':'http', 'method':'GET', 'path':'/api/events', 'headers':[(b'cookie', f'{COOKIE}={a}'.encode())], 'app':app, 'query_string':b''}
        request = Request(scope); request.state.visitor_id = a
        def event(cid): return 'event: case_changed\ndata: '+json.dumps({'case_id': cid})+'\n\n'
        assert event_visible(request, event(ac))
        assert not any(event_visible(request, event(cid)) for cid in (bc, oc, sc))
        app.state.pending_cases['pending-b'] = b
        assert not event_visible(request, event('pending-b'))
        client.cookies.clear()
        client.get('/api/session')
        assert client.post('/api/admin/login', json={'passcode':'secret'}).status_code == 200
        listed = {case['id'] for case in client.get('/api/cases').json()}
        assert listed == {oc, sc}
        assert client.get(f'/api/cases/{bc}').status_code == 404
        assert client.get(f'/api/cases/{sc}').status_code == 200


def test_visitor_retention_deletes_case_children_and_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr('backend.app.privacy.ROOT', tmp_path)
    app = create_app(Settings(database_url=f'sqlite:///{tmp_path}/db'))
    with TestClient(app, base_url='https://testserver') as client:
        client.get('/api/session'); visitor = client.cookies.get(COOKIE)
        old = datetime.now(timezone.utc) - timedelta(days=8)
        with Session(app.state.engine) as db:
            case = Case(title='Expired', owner_id=visitor, created_at=old)
            owner = Case(title='Owner', owner_id='owner', created_at=old)
            db.add_all([case, owner]); db.commit(); cid = case.id; owner_id = owner.id
            folder = tmp_path / 'var' / 'evidence' / cid; folder.mkdir(parents=True)
            path = folder / 'image'; path.write_bytes(b'private')
            db.add(Evidence(case_id=cid, kind='screenshot', path=str(path)))
            db.add(Event(case_id=cid, actor='user', type='test', title='Test'))
            db.add(Message(case_id=cid, direction='in', to='a', from_='b', subject='s', body_text='private'))
            db.commit()
        assert client.get(f'/api/cases/{cid}').status_code == 404
        assert delete_expired(app.state.engine) == 1
        assert not path.exists()
        with Session(app.state.engine) as db:
            assert db.get(Case, cid) is None and db.get(Case, owner_id) is not None
            assert not db.exec(select(Evidence).where(Evidence.case_id == cid)).all()
            assert not db.exec(select(Message).where(Message.case_id == cid)).all()
            assert not db.exec(select(Event).where(Event.case_id == cid)).all()


def test_sse_stream_drops_other_visitors_events(tmp_path):
    import asyncio
    app = create_app(Settings(database_url=f'sqlite:///{tmp_path}/db'))
    with TestClient(app, base_url='https://testserver'):
        a, b = str(uuid4()), str(uuid4())
        with Session(app.state.engine) as db:
            acase, bcase = Case(title='A', owner_id=a), Case(title='B', owner_id=b)
            db.add_all([acase, bcase]); db.commit(); aid, bid = acase.id, bcase.id
        route = next(r for r in app.routes if getattr(r, 'path', None) == '/api/events')
        async def exercise():
            scope = {'type':'http', 'method':'GET', 'path':'/api/events', 'headers':[(b'cookie', f'{COOKIE}={a}'.encode())], 'app':app, 'query_string':b''}
            async def receive():
                await asyncio.sleep(3600)
            request = Request(scope, receive); request.state.visitor_id = a
            response = await route.endpoint(request)
            stream = response.body_iterator
            assert await anext(stream) == ': connected\n\n'
            await app.state.events.publish('case_changed', {'case_id':bid, 'reason':'private'})
            await app.state.events.publish('case_changed', {'case_id':aid, 'reason':'visible'})
            result = await asyncio.wait_for(anext(stream), 1)
            assert aid in result and bid not in result and 'private' not in result
            await stream.aclose()
        asyncio.run(exercise())


def test_authorized_screenshot_has_browser_content_type(tmp_path):
    app=create_app(Settings(database_url=f'sqlite:///{tmp_path}/db',admin_passcode='owner-secret'))
    with TestClient(app,base_url='https://testserver') as client:
        client.get('/api/session');visitor=client.cookies.get(COOKIE)
        image=tmp_path/'upload.image';image.write_bytes(b'\x89PNG\r\n\x1a\nfixture')
        with Session(app.state.engine) as db:
            case=Case(title='Screenshot',owner_id=visitor);db.add(case);db.commit();cid=case.id
            evidence=Evidence(case_id=cid,kind='screenshot',path=str(image));db.add(evidence);db.commit();eid=evidence.id
        url=f'/api/cases/{cid}/evidence/{eid}/file'
        response=client.get(url);assert response.status_code==200 and response.headers['content-type']=='image/png'
        assert client.get(url,headers={'cookie':f'{COOKIE}={uuid4()}'}).status_code==404
        client.post('/api/admin/login',json={'passcode':'owner-secret'})
        assert client.get(url).status_code==404
        with Session(app.state.engine) as db:
            case=db.get(Case,cid);case.owner_id='owner';db.add(case);db.commit()
        assert client.get(url).headers['content-type']=='image/png'
