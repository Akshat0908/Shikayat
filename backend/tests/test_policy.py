import pytest
from backend.app.engine.policy import decide

@pytest.mark.parametrize('category,kwargs,action',[
 ('acknowledged',{},'wait'),('auto_reply',{},'wait'),('deflection',{},'followup'),
 ('deflection',{'deflections':2},'escalate'),('rejected',{},'escalate'),
 ('info_requested',{'missing_info':True},'ask_user'),('info_requested',{},'reply_info'),
 ('resolution_offered',{'offered':4299,'demand':4299},'confirm_receipt'),
 ('partial_resolution',{},'offer_choice'),('acknowledged',{'ack_breached':True},'followup'),('acknowledged',{'ack_breached':True,'followups':1},'escalate'),
 ('resolution_offered',{'receipt_confirmed':True},'resolve')])
def test_transitions(category: str, kwargs: dict, action: str) -> None:
    decision=decide('L2',category,**kwargs)
    assert decision.action==action and decision.reason

def test_filing() -> None:
    assert decide('L3','rejected').level=='L4'
    assert decide('L3','rejected').action=='prepare_filing'
    assert decide('L4','rejected').action=='wait'

@pytest.mark.parametrize('sector',['banking','insurance','telecom','travel',None])
def test_non_ecommerce_requires_review(sector):
    decision=decide('L2','deflection',deflections=2,ack_breached=True,sector=sector)
    assert decision.action=='user_review'
    assert 'Sector-specific rules not configured' in decision.reason


def test_active_chargeback_requires_review_before_followup():
    decision=decide('L2','deflection',chargeback_pending=True)
    assert decision.action=='user_review' and 'bank' in decision.reason.lower()
