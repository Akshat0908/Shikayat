from backend.app.ai.classify_reply import ReplyAnalysis, enforce_forensics


def test_hallucinated_partial_offer_is_not_shown_to_user():
    analysis=ReplyAnalysis(reply_type='partial_offer',acknowledged=True,original_remedy='refund',promised_action=None,refund_confirmed=False,offered_amount_inr=200,resolution_status='partially_resolved',evidence_quotes=[],next_action='Accept the offer',reason='An offer was made')
    result=enforce_forensics(analysis,'We regret the inconvenience. Your complaint has been forwarded to the team.',4299,'refund')
    assert result.reply_type=='deflection'
    assert result.offered_amount_inr is None
    assert result.resolution_status=='unresolved'
    assert result.category=='deflection'
