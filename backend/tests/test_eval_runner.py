import asyncio
import json
from collections import Counter
from pathlib import Path
import pytest
from eval.run_eval import BudgetExceeded, Meter, Baseline, score

ROOT=Path(__file__).resolve().parents[2]

def test_fixture_mix_and_labels_are_separate():
    cases=[json.loads(path.read_text()) for path in sorted((ROOT/'eval/cases').glob('*.json'))]
    assert len(cases)==20
    assert Counter(case['category'] for case in cases)=={'resolution':5,'deflection':5,'partial offer':4,'wrong-sector trap':3,'ambiguous':3}
    assert all(set(case['inputs'])=={'complaint','reply','received_at'} for case in cases)
    assert all(set(case['ground_truth'])=={'recipient','rule','deadline','reply_type','next_action'} for case in cases)

def test_deterministic_scoring_requires_all_fields():
    truth={'recipient':None,'rule':None,'deadline':None,'reply_type':'deflection','next_action':'user_review'}
    assert all(score(truth,truth).values())
    output={**truth,'rule':'ecom_rules_2020_grievance'}
    assert not score(output,truth)['rule'] and not score(output,truth)['end_to_end']

def test_budget_guard_stops_before_api_call():
    meter=Meter('gpt-5.4',{'input':2.5,'output':15},'unused')
    meter.spent=4.999
    with pytest.raises(BudgetExceeded):
        asyncio.run(meter.call('test','gpt-5.4',Baseline,'instructions','complaint'))


def test_safe_review_and_ask_user_are_accepted_symmetrically():
    base={'recipient':None,'rule':None,'deadline':None,'reply_type':'partial_offer','next_action':'offer_choice'}
    assert score({**base,'next_action':'user_review'},base)['next_action']
    for expected,actual in [('confirm_receipt','user_review'),('user_review','ask_user')]:
        truth={**base,'next_action':expected}
        assert score({**truth,'next_action':actual},truth)['next_action']
    assert not score({**base,'next_action':'wait'},base)['next_action']
