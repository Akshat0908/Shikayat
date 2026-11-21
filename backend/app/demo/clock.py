from datetime import datetime, timedelta, timezone
from sqlmodel import Session
from ..models import Settings

def now(session: Session) -> datetime:
    settings=session.get(Settings,1)
    return datetime.now(timezone.utc)+timedelta(seconds=settings.demo_clock_offset_seconds if settings else 0)
