"""Record matching decisions without logging message bodies or credentials."""
import json
import logging
from datetime import datetime, timezone
from ..config import ROOT

logger=logging.getLogger(__name__)


def decision(case_id: str, message_id: str | None, method: str | None, outcome: str, reason: str) -> None:
    entry={'at':datetime.now(timezone.utc).isoformat(),'case_id':case_id,'message_id':message_id,'match_method':method,'decision':outcome,'reason':reason}
    try:
        path=ROOT/'var'/'verification'/'attach_decisions.log'
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('a',encoding='utf-8') as stream: stream.write(json.dumps(entry)+'\n')
    except OSError:
        logger.warning('Unable to write attach decision log')
