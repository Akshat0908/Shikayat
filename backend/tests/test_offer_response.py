from fastapi.testclient import TestClient
from sqlmodel import Session,select
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import Case,CaseStatus,Message,Event
from backend.app.ai.draft_complaint import EmailDraft

def test_partial_offer_requires_choice_and_counter_is_approval_gated(tmp_path,monkeypatch):
    async def draft(facts,thread,reason,deadline):
        return EmailDraft(subject='Counter',body=reason,cited_refs=[],attachments=[],demand='refund',deadline_date=deadline)
    monkeypatch.setattr('backend.app.ai.draft_escalation.draft_escalation',draft)
    app=create_app(Settings(database_url=f'sqlite:///{tmp_path}/offer.db'))
    with TestClient(app) as client:
        with Session(app.state.engine) as session:
            case=Case(title='Refund',status=CaseStatus.NEEDS_INFO);session.add(case);session.commit();id=case.id
            session.add(Message(case_id=id,direction='in',to='user@example.test',from_='demo@example.test',subject='Offer',body_text='Voucher',classification_json={'reply_type':'partial_offer'}));session.commit()
        assert client.post(f'/api/cases/{id}/offer-response',json={'action':'counter'}).status_code==422
        result=client.post(f'/api/cases/{id}/offer-response',json={'action':'counter','counter_amount':1000})
        assert result.status_code==200 and result.json()['status']=='awaiting_approval'
        with Session(app.state.engine) as session:
            assert session.get(Case,id).status==CaseStatus.AWAITING_APPROVAL
            assert session.exec(select(Event).where(Event.case_id==id,Event.type=='offer_response')).first()
