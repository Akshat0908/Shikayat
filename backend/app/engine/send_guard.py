"""Shared send limits for approved and automated case mail."""
from datetime import datetime, timedelta, timezone
from ..models import Case, CaseStatus, Message
from ..config import Settings


def guard(case: Case, messages: list[Message], current: datetime, config: Settings, demo: bool, contact: dict | None = None) -> tuple[str | None, datetime | None]:
    if case.facts_json.get('looks_like_sample'):
        address = (contact or {}).get('email', '').strip().casefold()
        allowlist = {s.strip().casefold() for s in config.autopilot_allowlist.split(',') if s.strip()}
        sandbox = config.demo_company_email.strip().casefold()
        if not (case.owner_id == 'owner' and case.facts_json.get('demo_sample') and demo and config.demo_mode
                and (contact or {}).get('verified') and sandbox and address == sandbox and address in allowlist):
            return 'Test evidence; use a sandbox preview only.', None
    if case.facts_json.get('sample_scan_complete') is False: return 'Screenshot sample-data check is incomplete.', None
    if case.status == CaseStatus.RESOLVED: return 'Case is resolved.', None
    if case.facts_json.get('paused'): return 'Case is paused by the user.', None
    if case.facts_json.get('recipient_bounced'): return 'Recipient bounced; emailing stopped.', None
    if case.facts_json.get('possible_bounce'): return 'Possible delivery failure awaiting your confirmation.', None
    if case.level.value not in ('L2','L3'): return 'Company escalation route exhausted; prepare the NCH-ready pack.', None
    promise=case.facts_json.get('promise')
    if promise:
        until=promise.get('redress_at') if promise.get('exceeds_redress') and promise.get('pushback_sent') else promise.get('grace_until') if not promise.get('exceeds_redress') else None
        if until:
            due=datetime.fromisoformat(until)
            if due.tzinfo is None: due=due.replace(tzinfo=timezone.utc)
            if current<due:
                from .promises import promise_is_real
                return ('Waiting for the company promise or redressal deadline.' if promise_is_real(promise,messages) else 'Waiting for the scheduled check-back.'),due
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
