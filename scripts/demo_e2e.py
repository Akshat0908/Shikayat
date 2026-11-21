"""Real SMTP → demo bot → IMAP → AI/policy acceptance. Never injects replies."""
import argparse
import sys
from datetime import datetime,timezone
sys.path.insert(0,str(__import__("pathlib").Path(__file__).resolve().parents[1]))
import json
import time
from pathlib import Path
import httpx


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://localhost:8000');parser.add_argument('--wait-seconds',type=int,default=300);args=parser.parse_args()
    started=time.monotonic()
    since=datetime.now(timezone.utc)
    with httpx.Client(base_url=args.url,timeout=120) as client:
        def post(path: str) -> dict:
            response=client.post(path)
            if response.is_error: raise RuntimeError(f'{path}: HTTP {response.status_code}: {response.text}')
            return response.json()
        case=post('/api/cases/sample/shopkart');id=case['id']
        print('Case:',id,'mode:',case['mode'],'strength:',case['strength_label'],flush=True)
        assert case['mode']=='live',case['facts_json'].get('replay_reason')
        assert case['amount_inr']==4299 and case['strength_label']=='Strong'
        post(f'/api/cases/{id}/draft');post(f'/api/cases/{id}/confirm-recipient');post(f'/api/cases/{id}/approve')
        print('PASS complaint approved; SMTP accepted',flush=True)
        end=started+args.wait_seconds
        seen=set()
        while time.monotonic()<end:
            response=client.get(f'/api/cases/{id}/verification');response.raise_for_status();audit=response.json()
            for event in audit['events']:
                if event['id'] not in seen:
                    seen.add(event['id'])
                    print('EVENT',event['at'],event['type'],event['title'],flush=True)
            if audit['case']['status']=='AWAITING_APPROVAL':
                print('Approving pending demo draft',flush=True)
                post(f'/api/cases/{id}/approve')
            if audit['case']['status']=='AWAITING_RECEIPT': break
            time.sleep(5)
        else: raise TimeoutError(f'No full resolution offer within {args.wait_seconds} seconds')
        messages=audit['messages'];incoming=[m for m in messages if m['direction']=='in'];outgoing=[m for m in messages if m['direction']=='out']
        assert len(incoming)==3 and len(outgoing)==3,(len(incoming),len(outgoing))
        assert [m['classification']['category'] for m in incoming]==['deflection','deflection','resolution_offered']
        assert all(m['in_reply_to'] in {o['message_id'] for o in outgoing} for m in incoming)
        assert any(e['payload_json'].get('action')=='escalate' for e in audit['events'])
        assert len([e for e in audit['events'] if e['type']=='bot_replied'])==3
        for e in audit['events']:
            if e['type'] in ('reply','bot_replied'): print('PASS',e['type'],e['title'],'folder:',e['payload_json'].get('folder'),flush=True)
        result=post(f'/api/cases/{id}/confirm-receipt')
        assert result['status']=='RESOLVED' and result['recovered_inr']==4299
        directory=Path('var/verification');directory.mkdir(parents=True,exist_ok=True)
        (directory/f'{id}.json').write_text(json.dumps(audit,indent=2))
    from sqlmodel import Session,select
    from backend.app.config import get_settings
    from backend.app.db import build_engine
    from backend.app.models import LlmCall
    engine=build_engine(get_settings().database_url)
    with Session(engine) as session:
        calls=session.exec(select(LlmCall).where(LlmCall.at>=since)).all()
        metrics={'case_id':id,'elapsed_seconds':round(time.monotonic()-started,2),'llm_calls':len(calls),'cache_hits':sum(c.cached for c in calls),'llm_latency_ms':round(sum(c.latency_ms for c in calls),2),'estimated_cost_usd':round(sum(c.est_cost_usd for c in calls),8)}
    engine.dispose()
    (directory/f'{id}-metrics.json').write_text(json.dumps(metrics,indent=2))
    print('PASS hero flow resolved; '+json.dumps(metrics),flush=True)

if __name__=='__main__':
    try: main()
    except Exception as error:
        print(f'FAIL {type(error).__name__}: {error}',flush=True);raise SystemExit(1)
