import base64
from pathlib import Path
from io import BytesIO
from starlette.datastructures import Headers
from uuid import uuid4
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from sqlmodel import Session
from ..ai.extract_case import extract_case
from ..ai.schemas import CaseFacts
from ..ai.transcribe import transcribe
from ..config import ROOT
from ..engine.company import match_company
from ..engine.strength import strength, rationale
from ..models import Case, Evidence, Event

router=APIRouter(prefix='/api/cases')

async def create(request: Request, text: str, images: list[UploadFile], audio: UploadFile | None, replay: CaseFacts | None = None) -> Case:
    if not text.strip() and not images and not audio:
        raise HTTPException(422,'Provide text, screenshots or audio')
    if len(images)>3:
        raise HTTPException(422,'At most three screenshots')
    case=Case(title='Understanding your complaint')
    evidence=[]
    encoded=[]
    directory=ROOT/'var'/'evidence'/case.id
    directory.mkdir(parents=True,exist_ok=True)
    async def progress(stage: str) -> None:
        await request.app.state.events.publish('progress',{'case_id':case.id,'stage':stage})
    await progress('reading_screenshots')
    for image in images:
        if image.content_type not in ('image/png','image/jpeg','image/webp'):
            raise HTTPException(422,'Unsupported screenshot type')
        data=await image.read(10*1024*1024+1)
        if len(data)>10*1024*1024:
            raise HTTPException(413,'Screenshot exceeds 10 MB')
        path=directory/f'{uuid4()}.image';path.write_bytes(data)
        encoded.append(f'data:{image.content_type};base64,'+base64.b64encode(data).decode())
        evidence.append(Evidence(case_id=case.id,kind='screenshot',path=str(path)))
    await progress('transcribing')
    if audio:
        data=await audio.read(25*1024*1024+1)
        if len(data)>25*1024*1024:
            raise HTTPException(413,'Audio exceeds 25 MB')
        suffix=Path(audio.filename or 'audio.webm').suffix
        if suffix not in ('.webm','.mp3','.wav','.m4a','.ogg','.mp4'):
            raise HTTPException(422,'Unsupported audio format')
        path=directory/f'{uuid4()}{suffix}';path.write_bytes(data)
        transcript=await transcribe(path)
        text+='\n'+transcript
        evidence.append(Evidence(case_id=case.id,kind='voice',path=str(path),transcript=transcript))
    if text:
        evidence.append(Evidence(case_id=case.id,kind='text',transcript=text))
    try:
        facts=replay or await extract_case(text,encoded)
        await progress('finding_officer')
        company=await match_company(facts.company_name)
        await progress('assessing')
        score,label=strength(facts,len(evidence))
        reason='Synthetic sample replay; deterministic strength calculation.' if replay else await rationale(facts,score)
        case.title=facts.issue_summary_en
        case.company_id=company['id'] if company else None
        case.facts_json=facts.model_dump(mode='json')
        if replay:
            case.facts_json={**case.facts_json,'demo_sample':True}
        case.amount_inr=facts.amount_inr
        case.demand=facts.user_demand
        case.strength_score=score;case.strength_label=label
        with Session(request.app.state.engine) as session:
            session.add(case);session.commit()
            session.add_all(evidence)
            session.add(Event(case_id=case.id,actor='ai',type='understood',title='Case understood',reason=reason))
            session.commit();session.refresh(case)
        await progress('done')
        return case
    except ValueError as error:
        await progress('failed')
        raise HTTPException(503,str(error)) from error

@router.post('')
async def new_case(request: Request, images: list[UploadFile] = File(default=[]), audio: UploadFile | None = File(default=None), text: str = Form(default='')) -> Case:
    return await create(request,text,images,audio)

@router.post('/sample/{sample_id}')
async def sample(request: Request,sample_id: str) -> Case:
    if sample_id not in ('shopkart','food','airline'):
        raise HTTPException(404,'Sample not found')
    directory=ROOT/'data'/'samples'/sample_id
    facts=CaseFacts.model_validate_json((directory/'facts.json').read_text())
    image=UploadFile(file=BytesIO((directory/'order.png').read_bytes()),filename='order.png',headers=Headers({'content-type':'image/png'}))
    return await create(request,(directory/'text.txt').read_text(),[image],None,replay=facts)
