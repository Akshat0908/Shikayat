from datetime import datetime, timezone, timedelta
import pytest
from backend.app.ai.draft_complaint import EmailDraft,validate_draft
from backend.app.engine.deadlines import deadlines

def test_no_unverified_citations() -> None:
    draft=EmailDraft(subject='Refund',body='Please refund.',cited_refs=['invented'],attachments=[],demand='refund',deadline_date='2026-12-21')
    with pytest.raises(ValueError): validate_draft(draft,'2026-12-21')
    draft.cited_refs=[]
    assert validate_draft(draft,'2026-12-21')==draft

def test_deadlines() -> None:
    sent=datetime(2026,11,21,tzinfo=timezone.utc)
    assert deadlines(sent)['ack_48h']==sent+timedelta(hours=48)
    assert deadlines(sent)['resolve_30d']==sent+timedelta(days=30)

def test_month_is_calendar_month() -> None:
    from datetime import datetime, timezone
    sent=datetime(2026,1,31,tzinfo=timezone.utc)
    assert deadlines(sent)['resolve_30d'].date().isoformat()=='2026-02-28'

def test_generated_email_has_no_placeholder_and_uses_profile():
    from backend.app.ai.draft_complaint import prepare_email
    from backend.app.models import UserProfile
    draft=EmailDraft(subject='[subject]',body='Dear Team,\nPlease refund INR 4299.\n\nSincerely,\n[Your Name]\n[Your Contact Information]',cited_refs=[],attachments=[],demand='refund',deadline_date='2026-12-21')
    result=prepare_email(draft,{'amount_inr':4299,'order_id':'ABC','user_demand':'refund'},UserProfile(name='Akshat',email='user@example.test'),{'sector':'e-commerce'})
    assert '[' not in result.body and '[' not in result.subject
    assert 'INR' not in result.body and '₹4,299' in result.body
    assert 'Akshat' in result.body and 'user@example.test' in result.body
    assert 'Rule 4(5)' in result.body and result.cited_refs==['ecom_rules_2020_grievance']
    assert result.subject=='Grievance: Refund of ₹4,299 not received | Order ABC'


def test_draft_polish_dates_phone_and_rule_before_deadline():
    from backend.app.ai.draft_complaint import EmailDraft,prepare_email
    from backend.app.models import UserProfile
    draft=EmailDraft(subject='Draft',body='Bought on 2026-11-04. Please resolve by 2026-12-21.',cited_refs=[],attachments=[],demand='replacement',deadline_date='2026-12-21')
    facts={'amount_inr':1099,'order_id':'LF-261104-7821','user_demand':'replacement','issue_type':'damaged','purchase_channel':'brand_website'}
    result=prepare_email(draft,facts,UserProfile(name='Akshat',phone='06378200898',email='user@example.test'),None)
    assert result.subject=='Grievance: Replacement for defective item of ₹1,099 | Order LF-261104-7821'
    assert '4 Nov 2026' in result.body and '21 Dec 2026' in result.body
    assert '+91 63782 00898' in result.body and '2026-12-21' not in result.body
    assert result.body.index('Rule 4(5)') < result.body.index('21 Dec 2026')
