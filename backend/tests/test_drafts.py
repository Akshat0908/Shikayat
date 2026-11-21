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
