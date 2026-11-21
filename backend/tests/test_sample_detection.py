import asyncio
from datetime import datetime, timezone
from sqlmodel import Session
from backend.app.ai import sample_detection
from backend.app.config import Settings
from backend.app.db import build_engine,init_db
from backend.app.engine.send_guard import guard
from backend.app.models import Case, Evidence


def test_visible_demo_label_blocks_normal_send(tmp_path,monkeypatch):
    engine=build_engine(f'sqlite:///{tmp_path}/case.db');init_db(engine);path=tmp_path/'evidence';path.write_bytes(b'\x89PNGmock')
    with Session(engine) as session:
        case=Case(title='case');session.add(case);session.commit();session.refresh(case);case_id=case.id
        session.add(Evidence(case_id=case_id,kind='screenshot',path=str(path)));session.commit()
    async def scan(*args,**kwargs): return sample_detection.SampleLabels(labels=['SAMPLE CASE • DEMO DATA'])
    monkeypatch.setattr(sample_detection,'call_structured',scan)
    asyncio.run(sample_detection.ensure_sample_scan(engine,case_id))
    with Session(engine) as session:
        case=session.get(Case,case_id);assert case.facts_json['looks_like_sample'] is True
        reason,_=guard(case,[],datetime.now(timezone.utc),Settings(),False)
        assert 'sandbox preview only' in reason


def test_failed_scan_blocks_send(tmp_path,monkeypatch):
    engine=build_engine(f'sqlite:///{tmp_path}/case.db');init_db(engine);path=tmp_path/'image';path.write_bytes(b'\x89PNGmock')
    with Session(engine) as session:
        case=Case(title='case');session.add(case);session.commit();session.refresh(case);case_id=case.id;session.add(Evidence(case_id=case_id,kind='screenshot',path=str(path)));session.commit()
    async def fail(*args,**kwargs): raise RuntimeError('offline')
    monkeypatch.setattr(sample_detection,'call_structured',fail);asyncio.run(sample_detection.ensure_sample_scan(engine,case_id))
    with Session(engine) as session:
        case=session.get(Case,case_id);reason,_=guard(case,[],datetime.now(timezone.utc),Settings(),False)
        assert 'incomplete' in reason


def test_labelled_hero_only_sends_to_allowlisted_sandbox():
    now = datetime.now(timezone.utc)
    config = Settings(demo_mode=True, demo_company_email='sandbox@example.test', autopilot_allowlist='sandbox@example.test')
    case = Case(title='Sample', owner_id='owner', facts_json={'looks_like_sample':True, 'demo_sample':True, 'sample_scan_complete':True})
    valid = {'email':'sandbox@example.test', 'verified':True}
    assert guard(case, [], now, config, True, valid) == (None, None)
    for contact in ({'email':'real@example.test','verified':True}, {'email':'sandbox@example.test','verified':False}, None):
        assert guard(case, [], now, config, True, contact)[0]
    assert guard(case, [], now, config, False, valid)[0]
    visitor = case.model_copy(update={'owner_id':'visitor'})
    assert guard(visitor, [], now, config, True, valid)[0]
    other = case.model_copy(update={'facts_json':{'looks_like_sample':True}})
    assert guard(other, [], now, config, True, valid)[0]


def test_sandbox_transport_rejects_non_sandbox_recipient(monkeypatch):
    from backend.app.mail import smtp_send
    monkeypatch.setattr(smtp_send, 'get_settings', lambda: Settings(demo_mode=True, demo_company_email='sandbox@example.test', autopilot_allowlist='sandbox@example.test', send_enabled=True))
    import pytest
    with pytest.raises(ValueError, match='configured allowlisted sandbox'):
        asyncio.run(smtp_send.send_email({'email':'real@example.test','verified':True},'Test','Body',True,True,case_id='test',sandbox_test=True))
