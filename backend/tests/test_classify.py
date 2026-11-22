import pytest
from backend.app.ai.classify_reply import ReplyAnalysis,enforce_forensics

@pytest.mark.parametrize('text,kind,offered,demand,expected,confirmed',[
 ('Your concern was forwarded to the concerned team at the earliest.','acknowledgment',None,4299,'deflection',False),
 ('Refund of INR 4299 was credited. UTR: ABCD12345','substantive_resolution',4299,4299,'substantive_resolution',True),
 ('We offer a ₹300 voucher.','substantive_resolution',300,4299,'partial_offer',False),
 ('Please send the order receipt.','evidence_request',None,4299,'evidence_request',False),
 ('We reject your refund request.','rejection',None,4299,'rejection',False),
 ('This is an automated acknowledgment.','acknowledgment',None,4299,'acknowledgment',False),
 ('Aapka concern concerned team ko forwarded to kar diya hai.','acknowledgment',None,4299,'deflection',False),
 ('Your refund of ₹4299 has been initiated.','substantive_resolution',4299,4299,'substantive_resolution',False),
 ('We can refund INR 1000.','substantive_resolution',1000,4299,'partial_offer',False),
 ('Your refund was completed successfully.','substantive_resolution',None,4299,'substantive_resolution',True),
])
def test_adversarial_replies(text,kind,offered,demand,expected,confirmed):
    result=ReplyAnalysis(reply_type=kind,acknowledged=True,original_remedy='refund',promised_action=None,refund_confirmed=True,offered_amount_inr=offered,resolution_status='resolved',evidence_quotes=[text,'fabricated'],next_action='review',reason='test')
    checked=enforce_forensics(result,text,demand,'refund')
    assert checked.reply_type==expected
    assert checked.refund_confirmed is confirmed
    assert checked.original_remedy == 'Refund of ₹4,299'
    assert checked.evidence_quotes==[text] and checked.invalid_evidence_quotes==['fabricated']

@pytest.mark.parametrize('text,expected',[
    ('We regret the inconvenience. Your concern was forwarded.', 'deflection'),
    ('We are looking into your complaint.', 'deflection'),
    ('Your complaint has ticket DEMO-T205.', 'acknowledgment'),
    ('Your complaint will be addressed within 3 working days.', 'acknowledgment'),
])
def test_acknowledgment_and_concrete_details(text,expected):
    result=ReplyAnalysis(reply_type='deflection',acknowledged=False,original_remedy=None,promised_action=None,refund_confirmed=False,offered_amount_inr=None,resolution_status='unresolved',evidence_quotes=[],next_action='review',reason='test')
    checked=enforce_forensics(result,text,4299,'refund')
    assert checked.acknowledged is True
    assert checked.reply_type == expected

def test_recommended_action_is_not_a_company_commitment():
    text='We regret the inconvenience. Your concern was forwarded to the concerned team.'
    result=ReplyAnalysis(reply_type='acknowledgment',acknowledged=False,original_remedy=None,promised_action=None,refund_confirmed=False,offered_amount_inr=None,resolution_status='unresolved',evidence_quotes=[],next_action='follow up',reason='test',concrete_action='Ask for refund confirmation')
    assert enforce_forensics(result,text,4299,'refund').reply_type=='deflection'

def test_scripted_replies_support_followup_and_escalation():
    from backend.app.demo.company_bot import REPLIES
    for text in REPLIES[:2]:
        result=ReplyAnalysis(reply_type='deflection',acknowledged=False,original_remedy=None,promised_action=None,refund_confirmed=False,offered_amount_inr=None,resolution_status='unresolved',evidence_quotes=[],next_action='follow up',reason='test')
        checked=enforce_forensics(result,text,4299,'refund')
        assert checked.acknowledged and checked.reply_type=='deflection'
        assert checked.original_remedy=='Refund of ₹4,299'


def make_analysis(kind='acknowledgment',confirmed=False,action=None):
    return ReplyAnalysis(reply_type=kind,acknowledged=True,original_remedy=None,promised_action=None,refund_confirmed=confirmed,offered_amount_inr=None,resolution_status='unresolved',evidence_quotes=[],next_action='review',reason='test',concrete_action=action)


def test_courier_referral_is_not_a_remedy():
    text='Please contact the delivery partner directly about your missing parcel.'
    result=enforce_forensics(make_analysis(action='contact the delivery partner'),text,2300,'refund')
    assert result.reply_type=='deflection' and result.acknowledged


def test_untraceable_initiated_refund_requests_proof():
    text='Your refund has been initiated. Please wait for your bank to process it.'
    result=enforce_forensics(make_analysis('substantive_resolution'),text,2300,'refund')
    assert result.reply_type=='acknowledgment' and result.needs_refund_proof and not result.refund_confirmed
    from backend.app.engine.policy import decide
    assert decide('L2',result.category,needs_refund_proof=result.needs_refund_proof).action=='reply_info'


def test_completed_refund_evidence_overrides_model_false_without_assuming_receipt():
    text='Your refund of ₹2,300 was credited. UTR: ABCD123456.'
    result=enforce_forensics(make_analysis('substantive_resolution'),text,2300,'refund')
    assert result.refund_confirmed and result.reply_type=='substantive_resolution'
    from backend.app.engine.policy import decide
    assert decide('L2',result.category,offered=2300,demand=2300).action=='confirm_receipt'


def test_negative_credit_is_not_confirmed():
    text='The refund was not credited; a transaction reference is pending.'
    assert not enforce_forensics(make_analysis('substantive_resolution',True),text,2300,'refund').refund_confirmed
