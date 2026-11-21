"""Shared send limits for approved and automated case mail."""
from datetime import datetime, timedelta, timezone
from ..models import Case, CaseStatus, Message
from ..config import Settings


def guard(case: Case, messages: list[Message], current: datetime, config: Settings, demo: bool) -> tuple[str | None, datetime | None]:
    if case.status == CaseStatus.RESOLVED: return 'Case is resolved.', None
    if case.facts_json.get('paused'): return 'Case is paused by the user.', None
    if case.facts_json.get('recipient_bounced'): return 'Recipient bounced; emailing stopped.', None
    if case.level.value not in ('L2','L3'): return 'Company escalation route exhausted; prepare the NCH-ready pack.', None
    outbound=[m for m in messages if m.direction=='out']
    if len(outbound)>=config.max_outbound_per_case: return 'Outbound email limit reached.', None
    level_messages=[m for m in outbound if m.level==case.level]
    limit=config.grievance_followup_limit if case.level.value=='L2' else config.nodal_followup_limit
    if len(level_messages)>limit: return 'Follow-up limit reached at this level.', None
    if outbound:
        interval=timedelta(seconds=config.demo_outbound_interval_seconds) if demo and config.demo_mode else timedelta(hours=config.min_outbound_interval_hours)
        last=max(m.sent_at.replace(tzinfo=timezone.utc) if m.sent_at.tzinfo is None else m.sent_at for m in outbound)
        due=last+interval
        if current<due: return 'Minimum interval between outbound emails has not elapsed.', due
    return None,None
