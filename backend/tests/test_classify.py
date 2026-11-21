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
    assert checked.evidence_quotes==[text] and checked.invalid_evidence_quotes==['fabricated']
