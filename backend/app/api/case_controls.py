from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import Session, select, delete
from ..config import ROOT
from ..models import Case, CaseStatus, Deadline, Evidence, Event, Message

router=APIRouter(prefix='/api/cases')

@router.post('/{case_id}/pause')
@router.post('/{case_id}/resume')
async def pause_or_resume(case_id: str, request: Request) -> dict:
    from ..workers import _send_lock
    paused=request.url.path.endswith('/pause')
    pending=None; bounced=False
    async with _send_lock:
        with Session(request.app.state.engine) as session:
            case=session.get(Case,case_id)
            if not case: raise HTTPException(404,'Case not found')
            if case.status==CaseStatus.RESOLVED: raise HTTPException(409,'Resolved cases cannot be paused')
            pending=case.facts_json.get('pending_review')
            bounced=bool(case.facts_json.get('recipient_bounced'))
            case.facts_json={**case.facts_json,'paused':paused};session.add(case)
            if not paused and pending:
                case.facts_json={k:v for k,v in case.facts_json.items() if k!='pending_review'}
            session.add(Event(case_id=case_id,actor='user',type='paused' if paused else 'resumed',title='Case paused' if paused else 'Case resumed',reason='User paused outgoing actions.' if paused else 'User resumed the case.'));session.commit()
    await request.app.state.events.publish('case_changed',{'case_id':case_id})
    if not paused and (pending or bounced):
        from ..workers import act
        from ..ai.classify_reply import ReplyAnalysis
        await act(request.app,case_id,ReplyAnalysis.model_validate(pending) if pending else None)
    return {'paused':paused}

class ManualUpdate(BaseModel):
    text: str=Field(min_length=1,max_length=10000)

@router.post('/{case_id}/update')
async def manual_update(case_id: str, update: ManualUpdate, request: Request) -> dict:
    if not update.text.strip(): raise HTTPException(422,'Enter an update')
    with Session(request.app.state.engine) as session:
        case=session.get(Case,case_id)
        if not case: raise HTTPException(404,'Case not found')
        if case.status==CaseStatus.RESOLVED: raise HTTPException(409,'Case is resolved')
    from ..workers import receive
    await receive(request.app,{'case_id':case_id,'message_id':f'<reported-{uuid4()}>','sender':request.app.state.config.user_email,'subject':'User-reported update','body':update.text.strip(),'origin':'user-reported'})
    return {'status':'recorded'}

@router.delete('/{case_id}')
async def delete_case(case_id: str, request: Request) -> dict:
    from ..workers import _send_lock
    async with _send_lock:
        with Session(request.app.state.engine) as session:
            if not session.get(Case,case_id): raise HTTPException(404,'Case not found')
            evidence=session.exec(select(Evidence).where(Evidence.case_id==case_id)).all()
            root=(ROOT/'var'/'evidence').resolve()
            paths=[]
            for item in evidence:
                if item.path:
                    path=Path(item.path).resolve()
                    if path.is_relative_to(root): paths.append(path)
            for model in (Deadline,Evidence,Event,Message): session.exec(delete(model).where(model.case_id==case_id))
            session.exec(delete(Case).where(Case.id==case_id));session.commit()
            for path in paths: path.unlink(missing_ok=True)
            folder=root/case_id
            if folder.is_dir():
                try: folder.rmdir()
                except OSError: pass
    await request.app.state.events.publish('case_changed',{'case_id':case_id})
    return {'status':'deleted'}
