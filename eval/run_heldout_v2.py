"""Run the supplied held-out cases once with the existing prompts and scorer."""
import asyncio
import imaplib
import json
import os
import smtplib
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from eval.run_eval import ROOT, Baseline, Meter, no_mail, score
from backend.app.config import get_settings
from backend.app.ai import extract_case as extraction, classify_reply as forensics
from backend.app.ai.draft_complaint import verified_refs
from backend.app.engine.company import load_companies, match_company
from backend.app.engine.policy import decide
from backend.app.engine.sector import effective_sector

DEST=ROOT/'eval'/'heldout_v2'/'result.json'

async def run():
    if DEST.exists(): raise RuntimeError('Held-out result already exists; refusing a repeat run')
    os.environ['SEND_ENABLED']='false';os.environ['DEMO_COMPANY_EMAIL']=''
    config=get_settings();os.environ['MODEL_FAST']=config.model_smart;get_settings.cache_clear();config=get_settings()
    assert not config.send_enabled
    smtplib.SMTP=smtplib.SMTP_SSL=imaplib.IMAP4=imaplib.IMAP4_SSL=no_mail
    model=config.model_smart;rates=json.loads(config.model_rates_json)
    if model!='gpt-5.4' or rates.get(model,{}).get('input')!=2.5 or rates.get(model,{}).get('output')!=15: raise RuntimeError('Verify model rates before running')
    meter=Meter(model,rates[model],config.openai_api_key.get_secret_value())
    if not meter.key: raise RuntimeError('OPENAI_API_KEY is missing')
    extraction.call_structured=meter.call;forensics.call_structured=meter.call
    import backend.app.ai.client as client_module
    client_module.call_structured=meter.call
    fixtures=json.loads((ROOT/'eval/heldout_v2/cases.json').read_text())
    if len(fixtures)!=10: raise ValueError('Expected exactly 10 held-out cases')
    directory=[{'name':c['name'],'sector':c.get('sector'),'verified_grievance_email':c['grievance_officer'].get('email') if c['grievance_officer'].get('verified') else None} for c in load_companies() if not c.get('demo')]
    legal=[{'id':r['id'],'description':r['description'],'rule_number':r['rule_number']} for r in verified_refs()]
    cases=[]
    for fixture in fixtures:
        # Preserve every supplied field; labels are never included in model inputs.
        complaint=json.dumps({key:fixture[key] for key in ('complaint_text','company_name','sector','purchase_channel','order_reference','amount_inr')},ensure_ascii=False)
        reply=fixture['company_reply_email'];truth={key:fixture[key] for key in ('correct_recipient_role','ecommerce_rules_apply','reply_type','resolved','safest_next_action')}
        comparable={'rule':'ecom_rules_2020_grievance' if truth['ecommerce_rules_apply'] else None,'reply_type':truth['reply_type']}
        reply_scored = truth['reply_type'] in ('acknowledgment','deflection','evidence_request','partial_offer','substantive_resolution','rejection')
        case={'id':fixture['case_id'],'ground_truth':truth,'systems':{}}
        started=time.monotonic();before=meter.spent
        baseline_input=json.dumps({'complaint':complaint,'company_reply':reply,'complaint_received_at':None,'company_directory':directory,'verified_legal_refs':legal},ensure_ascii=False)
        base=await meter.call('eval_baseline',model,Baseline,'Analyze this consumer complaint and company reply. Select a verified recipient or null, applicable verified rule or null, applicable deadline as YYYY-MM-DD or null, reply classification, and the safest next action. Use only supplied information; ask for user review if necessary.',baseline_input)
        data=base.model_dump();scores=score(data,comparable)
        case['systems']['baseline']={'metrics':{'rule':scores['rule'],'reply_classification':scores['reply_classification'] if reply_scored else None},'output':data,'cost_usd':round(meter.spent-before,8),'latency_seconds':round(time.monotonic()-started,3)}
        started=time.monotonic();before=meter.spent
        facts=await extraction.extract_case(complaint,[]);company=await match_company(facts.company_name)
        sector=effective_sector(company,facts.model_dump(mode='json'));contact=(company or {}).get('grievance_officer') or {}
        rule='ecom_rules_2020_grievance' if sector=='e-commerce' and any(r['id']=='ecom_rules_2020_grievance' for r in legal) else None
        analysis=await forensics.classify_reply(reply,facts.amount_inr,facts.user_demand)
        decision=decide('L2',analysis.category,deflections=1 if analysis.category=='deflection' else 0,offered=analysis.offered_amount_inr,demand=facts.amount_inr,missing_info=bool(facts.missing_info),sector=sector,needs_refund_proof=analysis.needs_refund_proof,chargeback_pending=facts.chargeback_pending)
        data={'recipient':contact.get('email') if contact.get('verified') else None,'rule':rule,'deadline':None,'reply_type':analysis.reply_type,'next_action':decision.action,'reason':decision.reason,'case_facts':facts.model_dump(mode='json'),'reply_forensics':analysis.model_dump(mode='json')}
        scores=score(data,comparable)
        case['systems']['shikayat']={'metrics':{'rule':scores['rule'],'reply_classification':scores['reply_classification'] if reply_scored else None},'output':data,'cost_usd':round(meter.spent-before,8),'latency_seconds':round(time.monotonic()-started,3)}
        cases.append(case)
        print(f"{case['id']} baseline={case['systems']['baseline']['metrics']} shikayat={case['systems']['shikayat']['metrics']} spent=${meter.spent:.4f}",flush=True)
    return {'data_source':'measured','evaluated_at':datetime.now(timezone.utc).isoformat(),'model':model,'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'case_count':len(cases),'cases':cases,'total_cost_usd':round(meter.spent,8),'usage':meter.usage,'limitations':'Only rule applicability and compatible reply types are scored. The ambiguous reply label is outside the existing taxonomy and is unscored. Recipient roles, free-text actions, complaint-receipt deadlines, and resolution status require review.'}

def main():
    result=asyncio.run(run());DEST.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    for metric in ('rule','reply_classification'):
        print(metric,*(f"{sum(c['systems'][s]['metrics'][metric] is True for c in result['cases'])}/{sum(c['systems'][s]['metrics'][metric] is not None for c in result['cases'])}" for s in ('baseline','shikayat')))
    print(f"Total estimated cost: ${result['total_cost_usd']:.6f}")

if __name__=='__main__':
    try: main()
    except Exception as error: print(f'Held-out evaluation stopped: {type(error).__name__}: {error}',file=sys.stderr);raise SystemExit(1)
