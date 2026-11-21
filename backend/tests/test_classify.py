from backend.app.ai.classify_reply import ReplyAnalysis,enforce_deflection

def test_forwarding_is_not_resolution_action():
    result=ReplyAnalysis(category='acknowledged',ticket_id='T1',promised_date=None,offered_amount_inr=None,requested_info=[],is_templated=True,templated_signals=[],summary_hinglish='Forwarded',concrete_action='Forwarded to the concerned team')
    assert enforce_deflection(result,'We have forwarded your concern to the concerned team.').category=='deflection'
