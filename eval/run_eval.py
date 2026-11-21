"""Offline pipeline evaluation: only OpenAI API calls; no mailbox or SMTP access."""
import asyncio
import json
import os
import smtplib
import imaplib
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from openai import AsyncOpenAI
from pydantic import BaseModel
from backend.app.config import get_settings
from backend.app.ai import extract_case as extraction, classify_reply as forensics
from backend.app.ai.draft_complaint import verified_refs
from backend.app.engine.company import load_companies, match_company
from backend.app.engine.deadlines import deadlines
from backend.app.engine.policy import decide
from backend.app.engine.sector import effective_sector

ROOT = Path(__file__).resolve().parents[1]
METRICS = ('recipient','rule','deadline','reply_classification','next_action','end_to_end')
LIMIT = 5.0
MAX_OUTPUT = 2048

class Baseline(BaseModel):
    recipient: str | None
    rule: Literal['ecom_rules_2020_grievance'] | None
    deadline: str | None
    reply_type: Literal['acknowledgment','deflection','evidence_request','partial_offer','substantive_resolution','rejection'] | None
    next_action: Literal['confirm_receipt','followup','offer_choice','user_review','ask_user','wait','escalate','reply_info'] | None
    reasoning: str

class BudgetExceeded(RuntimeError): pass

class Meter:
    def __init__(self, model: str, rate: dict, key: str):
        self.model, self.rate, self.key = model, rate, key
        self.spent = 0.0
        self.usage = []
    async def call(self, task, model, schema, instructions, text, images=None, **kwargs):
        if model != self.model or images or kwargs:
            raise ValueError('Evaluation only permits the chosen model and text-only inputs')
        # One token per UTF-8 byte plus a generous envelope for API serialization.
        # Reserve the full output limit at the uncached rate before every call.
        input_bound=len((instructions+text+json.dumps(schema.model_json_schema(),ensure_ascii=False)).encode())+8192
        bound=(input_bound*self.rate['input']+MAX_OUTPUT*self.rate['output'])/1_000_000
        if self.spent+bound > LIMIT:
            raise BudgetExceeded(f'Next call could exceed ${LIMIT:.2f}; stopped before request')
        self.spent += bound
        started=time.monotonic()
        try:
            async with AsyncOpenAI(api_key=self.key, timeout=60, max_retries=0) as client:
                response=await client.responses.parse(model=model,instructions=instructions,input=[{'role':'user','content':[{'type':'input_text','text':text}]}],text_format=schema,max_output_tokens=MAX_OUTPUT,store=False)
            if not response.usage:
                raise RuntimeError('API did not report token usage; reserved cost retained')
            cost=(response.usage.input_tokens*self.rate['input']+response.usage.output_tokens*self.rate['output'])/1_000_000
            self.spent += cost-bound
            self.usage.append({'task':task,'input_tokens':response.usage.input_tokens,'output_tokens':response.usage.output_tokens,'cost_usd':cost,'latency_seconds':time.monotonic()-started})
            if response.output_parsed is None:
                raise RuntimeError('No structured output')
            return response.output_parsed
        except Exception:
            # If an API error has no usage, its conservative reservation remains charged.
            raise

def score(output: dict, truth: dict) -> dict:
    result={name: output.get(field)==truth.get(field) for name,field in [('recipient','recipient'),('rule','rule'),('deadline','deadline'),('reply_classification','reply_type'),('next_action','next_action')]}
    result['end_to_end']=all(result.values())
    return result

def aggregate(cases, system):
    return {key:sum(case[system]['metrics'][key] for case in cases) for key in METRICS}

def no_mail(*args, **kwargs):
    raise RuntimeError('Mail is disabled in evaluation')

async def run():
    os.environ['SEND_ENABLED']='false'
    os.environ['DEMO_COMPANY_EMAIL']=''
    config=get_settings(); os.environ['MODEL_FAST']=config.model_smart; get_settings.cache_clear(); config=get_settings()
    assert not config.send_enabled
    smtplib.SMTP=smtplib.SMTP_SSL=imaplib.IMAP4=imaplib.IMAP4_SSL=no_mail
    model=config.model_smart
    rates=json.loads(config.model_rates_json)
    if model != 'gpt-5.4' or rates.get(model,{}).get('input')!=2.5 or rates.get(model,{}).get('output')!=15:
        raise RuntimeError('Verify the current model rates and update the evaluation budget guard before running')
    meter=Meter(model,rates[model],config.openai_api_key.get_secret_value())
    if not meter.key: raise RuntimeError('OPENAI_API_KEY is missing')
    # Route both unmodified pipeline prompts through the same bounded client and model.
    extraction.call_structured=meter.call; forensics.call_structured=meter.call
    import backend.app.ai.client as client_module
    client_module.call_structured=meter.call
    fixtures=[json.loads(path.read_text()) for path in sorted((ROOT/'eval/cases').glob('*.json'))]
    if len(fixtures)!=20: raise ValueError('Expected exactly 20 evaluation cases')
    directory=[{'name':c['name'],'sector':c.get('sector'),'verified_grievance_email':c['grievance_officer'].get('email') if c['grievance_officer'].get('verified') else None} for c in load_companies() if not c.get('demo')]
    legal=[{'id':r['id'],'description':r['description'],'rule_number':r['rule_number']} for r in verified_refs()]
    cases=[]
    for fixture in fixtures:
        inputs=fixture['inputs']; truth=fixture['ground_truth']; result={'id':fixture['id'],'category':fixture['category']}
        started=time.monotonic();before=meter.spent
        # Only complaint inputs and the same public directory/legal context are provided; no labels.
        baseline_input=json.dumps({'complaint':inputs['complaint'],'company_reply':inputs['reply'],'complaint_received_at':inputs['received_at'],'company_directory':directory,'verified_legal_refs':legal},ensure_ascii=False)
        base=await meter.call('eval_baseline',model,Baseline,'Analyze this consumer complaint and company reply. Select a verified recipient or null, applicable verified rule or null, applicable deadline as YYYY-MM-DD or null, reply classification, and the safest next action. Use only supplied information; ask for user review if necessary.',baseline_input)
        base_data=base.model_dump();result['baseline']={'metrics':score(base_data,truth),'output':json.dumps(base_data,ensure_ascii=False,indent=2),'cost_usd':round(meter.spent-before,8),'latency_seconds':round(time.monotonic()-started,3)}
        started=time.monotonic();before=meter.spent
        facts=await extraction.extract_case(inputs['complaint'],[])
        company=await match_company(facts.company_name)
        sector=effective_sector(company,facts.model_dump(mode='json'))
        contact=(company or {}).get('grievance_officer') or {}
        recipient=contact.get('email') if contact.get('verified') else None
        received=datetime.fromisoformat(inputs['received_at']) if inputs['received_at'] else None
        rule='ecom_rules_2020_grievance' if sector=='e-commerce' and any(r['id']=='ecom_rules_2020_grievance' for r in legal) else None
        due=deadlines(received)['resolve_30d'].date().isoformat() if rule and received else None
        analysis=await forensics.classify_reply(inputs['reply'],facts.amount_inr,facts.user_demand)
        decision=decide('L2',analysis.category,deflections=1 if analysis.category=='deflection' else 0,offered=analysis.offered_amount_inr,demand=facts.amount_inr,missing_info=bool(facts.missing_info),sector=sector)
        output={'recipient':recipient,'rule':rule,'deadline':due,'reply_type':analysis.reply_type,'next_action':decision.action,'reason':decision.reason,'case_facts':facts.model_dump(mode='json'),'reply_forensics':analysis.model_dump(mode='json')}
        result['shikayat']={'metrics':score(output,truth),'output':json.dumps(output,ensure_ascii=False,indent=2),'cost_usd':round(meter.spent-before,8),'latency_seconds':round(time.monotonic()-started,3)}
        cases.append(result)
        print(f"{fixture['id']} baseline={sum(result['baseline']['metrics'].values())}/6 shikayat={sum(result['shikayat']['metrics'].values())}/6 spent=${meter.spent:.4f}",flush=True)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    timestamp=datetime.now(timezone.utc)
    return {'data_source':'measured','evaluated_at':timestamp.isoformat(),'model':model,'commit':commit,'case_count':len(cases),'cases':cases,'total_cost_usd':round(meter.spent,8),'usage':meter.usage,'methodology':'Synthetic text-only cases; identical model; costs use uncached token rates; SMTP and IMAP disabled; no retries or cached evaluations.'}

def main():
    result=asyncio.run(run())
    path=ROOT/'eval/results'/f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    baseline=aggregate(result['cases'],'baseline'); pipeline=aggregate(result['cases'],'shikayat')
    print('| Metric | Baseline | Shikayat |\n|---|---:|---:|')
    for metric in METRICS: print(f"| {metric} | {baseline[metric]}/20 | {pipeline[metric]}/20 |")
    print(f"Total: ${result['total_cost_usd']:.6f}; result: {path}")

if __name__=='__main__':
    try: main()
    except Exception as error:
        print(f'Evaluation stopped: {type(error).__name__}: {error}',file=sys.stderr)
        raise SystemExit(1)
