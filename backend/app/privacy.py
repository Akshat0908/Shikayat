"""Visitor-scoped case access and retention, using real wall-clock time."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4
from fastapi import Request
from sqlmodel import Session, select, delete
from .config import ROOT
from .models import Case, Deadline, Evidence, Event, Message
from .api.admin import is_admin

COOKIE = 'shikayat_visitor'
RETENTION = timedelta(days=7)


def visitor_id(request: Request) -> str:
    value = request.cookies.get(COOKIE, '')
    try:
        parsed = UUID(value)
        if parsed.version == 4 and str(parsed) == value:
            return value
    except (ValueError, AttributeError):
        pass
    return str(uuid4())


def request_owner(request: Request) -> str:
    return 'owner' if is_admin(request) else request.state.visitor_id


def expired(case: Case) -> bool:
    created = case.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return case.owner_id != 'owner' and created <= datetime.now(timezone.utc) - RETENTION


def visible(request: Request, case: Case) -> bool:
    if expired(case):
        return False
    if is_admin(request):
        return case.owner_id == 'owner' or bool(case.facts_json.get('demo_sample'))
    return case.owner_id == request.state.visitor_id


def event_visible(request: Request, message: str) -> bool:
    try:
        event = next(line[7:] for line in message.splitlines() if line.startswith('event: '))
        data = json.loads(next(line[6:] for line in message.splitlines() if line.startswith('data: ')))
        if event == 'ping':
            return True
        case_id = data.get('case_id')
        if not case_id:
            return is_admin(request)
        with Session(request.app.state.engine) as session:
            case = session.get(Case, case_id)
            if case:
                return visible(request, case)
        return request.app.state.pending_cases.get(case_id) == request_owner(request)
    except (StopIteration, ValueError, TypeError, AttributeError):
        return False


def delete_cases(engine, ids: list[str]) -> int:
    if not ids:
        return 0
    with Session(engine) as session:
        root = (ROOT / 'var' / 'evidence').resolve()
        paths = []
        for item in session.exec(select(Evidence).where(Evidence.case_id.in_(ids))).all():
            if item.path:
                path = Path(item.path).resolve()
                if path.is_relative_to(root):
                    paths.append(path)
        for model in (Deadline, Evidence, Event, Message):
            session.exec(delete(model).where(model.case_id.in_(ids)))
        session.exec(delete(Case).where(Case.id.in_(ids)))
        session.commit()
    for path in paths:
        path.unlink(missing_ok=True)
    for case_id in ids:
        folder = root / case_id
        if folder.is_dir():
            try:
                folder.rmdir()
            except OSError:
                pass
    return len(ids)


def delete_expired(engine) -> int:
    with Session(engine) as session:
        ids = [case.id for case in session.exec(select(Case)).all() if expired(case)]
    return delete_cases(engine, ids)


async def retention_loop(app) -> None:
    while True:
        try:
            await asyncio.to_thread(delete_expired, app.state.engine)
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Case retention cleanup failed')
        await asyncio.sleep(300)
