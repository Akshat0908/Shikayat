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
from ..config import ROOT, get_settings
from ..engine.company import match_company, provisional_company
from ..engine.strength import strength, rationale
from ..models import Case, Evidence, Event

router=APIRouter(prefix='/api/cases')

async def create(request: Request, text: str, images: list[UploadFile], audio: UploadFile | None, replay: CaseFacts | None = None) -> dict:
    if not text.strip() and not images and not audio:
        raise HTTPException(422,'Provide text, screenshots or audio')
    if len(images)>3:
        raise HTTPException(422,'At most three screenshots')
    case=Case(title='Understanding your complaint')
    evidence=[]
    original_text=text
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
    if original_text:
        evidence.append(Evidence(case_id=case.id,kind='text',transcript=original_text))
    try:
        mode='live'
        replay_reason=None
        if replay and (get_settings().replay_mode or not get_settings().openai_api_key.get_secret_value()):
            facts=replay;mode='replay';replay_reason='Explicit replay mode or API key unavailable'
        else:
            try:
                facts=await extract_case(text,encoded)
            except Exception as error:
                if replay is None: raise
                facts=replay;mode='replay';replay_reason=f'Extraction API failed: {type(error).__name__}'

        await progress('finding_officer')
        company=await match_company(facts.company_name)
        if not company and facts.company_name: company=provisional_company(facts.company_name)
        await progress('assessing')
        score,label=strength(facts,len(evidence))
        reason='Synthetic sample replay; deterministic strength calculation.' if mode=='replay' else await rationale(facts,score)
        fact_values=facts.model_dump(mode='json')
        records=[]
        for field in ('company_name','order_id','amount_inr','purchase_date','issue_type','issue_summary_en','user_demand','events','contact_attempts','days_elapsed'):
            value=fact_values.get(field)
            if value is None or value==[]: continue
            sources=[item for item in facts.provenance if item.field==field]
            if not sources:
                records.append({'field':field,'value':value,'origin':None,'source_excerpt':None,'bbox':None,'verification_state':'needs_verification'})
            for source in sources:
                verified=source.origin=='text' and bool(source.source_excerpt) and source.source_excerpt in text
                records.append({'field':field,'value':value,'origin':source.origin,'source_excerpt':source.source_excerpt,'bbox':source.bbox,'verification_state':'verified' if verified else 'needs_verification'})
        evidence.append(Evidence(case_id=case.id,kind='ledger',extracted_json={'facts':records}))
        case.title=facts.issue_summary_en
        case.company_id=company['id'] if company else None
        case.facts_json={**facts.model_dump(mode='json'),'mode':mode,'replay_reason':replay_reason,'known_ticket_ids':[attempt.ticket_id for attempt in facts.contact_attempts if attempt.ticket_id]}
        if replay:
            case.facts_json={**case.facts_json,'demo_sample':True}
        case.amount_inr=facts.amount_inr
        case.demand=facts.user_demand
        case.strength_score=score;case.strength_label=label
        with Session(request.app.state.engine) as session:
            session.add(case);session.commit()
            session.add_all(evidence)
            session.add(Event(case_id=case.id,actor='ai',type='understood',title='Case understood',reason=reason,payload_json={'mode':mode,'replay_reason':replay_reason}))
            session.commit();session.refresh(case)
        from ..ai.sample_detection import ensure_sample_scan
        await ensure_sample_scan(request.app.state.engine,case.id)
        with Session(request.app.state.engine) as session:
            case=session.get(Case,case.id)
        await progress('done')
        return {**case.model_dump(mode="json"),"mode":mode}
    except ValueError as error:
        await progress('failed')
        raise HTTPException(503,str(error)) from error

@router.post('')
async def new_case(request: Request, images: list[UploadFile] = File(default=[]), audio: UploadFile | None = File(default=None), text: str = Form(default='')) -> dict:
    return await create(request,text,images,audio)

@router.post('/sample/{sample_id}')
async def sample(request: Request,sample_id: str) -> dict:
    if sample_id not in ('shopkart','food','airline'):
        raise HTTPException(404,'Sample not found')
    directory=ROOT/'data'/'samples'/sample_id
    facts=CaseFacts.model_validate_json((directory/'facts.json').read_text())
    image=UploadFile(file=BytesIO((directory/'order.png').read_bytes()),filename='order.png',headers=Headers({'content-type':'image/png'}))
    return await create(request,(directory/'text.txt').read_text(),[image],None,replay=facts)

@router.get('/{case_id}/evidence')
def case_evidence(case_id: str, request: Request) -> dict:
    from sqlmodel import select
    with Session(request.app.state.engine) as session:
        if not session.get(Case,case_id): raise HTTPException(404,'Case not found')
        ledger=session.exec(select(Evidence).where(Evidence.case_id==case_id,Evidence.kind=='ledger')).all()
        return {'case_id':case_id,'facts':[fact for item in ledger for fact in item.extracted_json.get('facts',[])]}

@router.get('/{case_id}/evidence/{evidence_id}/file')
def evidence_file(case_id: str,evidence_id: str,request: Request):
    from fastapi.responses import FileResponse
    with Session(request.app.state.engine) as session:
        item=session.get(Evidence,evidence_id)
        if not item or item.case_id!=case_id or item.kind not in ('screenshot','voice') or not item.path or not Path(item.path).is_file():
            raise HTTPException(404,'Evidence file not found')
        return FileResponse(item.path)
