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
