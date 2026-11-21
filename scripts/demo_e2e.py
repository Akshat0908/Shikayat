"""Live API acceptance: requires configured AI pricing/models and Gmail mailboxes.

Run twice against `make dev`; inspect LlmCall.cached for replay cache hits.
This script sends real approved complaint emails to the configured demo mailbox.
"""
import argparse
import time
import httpx

def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://localhost:8000');args=parser.parse_args()
    started=time.monotonic()
    with httpx.Client(base_url=args.url,timeout=120) as client:
        def post(path: str, **kwargs: object) -> dict:
            response=client.post(path,**kwargs);response.raise_for_status();return response.json()
        case=post('/api/cases/sample/shopkart');id=case['id']
        assert case['amount_inr']==4299 and case['strength_label']=='Strong'
        post(f'/api/cases/{id}/draft');post(f'/api/cases/{id}/approve')
        for expected in ('WAITING','ESCALATED','AWAITING_RECEIPT'):
            post('/api/demo/inject',json={'case_id':id})
            response=client.get(f'/api/cases/{id}');response.raise_for_status()
            assert response.json()['status']==expected,response.text
        result=post(f'/api/cases/{id}/confirm-receipt')
        assert result['status']=='RESOLVED' and result['recovered_inr']==4299
    print(f'Hero flow passed in {time.monotonic()-started:.2f}s')

if __name__=='__main__': main()
