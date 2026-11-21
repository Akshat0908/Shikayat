from calendar import monthrange
from datetime import datetime, timedelta


def deadlines(received_at: datetime) -> dict[str, datetime]:
    """Rule 4(5): calendar month from receipt, not a fixed 30 days."""
    year=received_at.year+(received_at.month==12)
    month=received_at.month%12+1
    due=received_at.replace(year=year,month=month,day=min(received_at.day,monthrange(year,month)[1]))
    return {'ack_48h':received_at+timedelta(hours=48),'resolve_30d':due}
