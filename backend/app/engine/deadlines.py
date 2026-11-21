from datetime import datetime, timedelta

def deadlines(sent_at: datetime) -> dict[str, datetime]:
    return {'ack_48h':sent_at+timedelta(hours=48),'resolve_30d':sent_at+timedelta(days=30)}
