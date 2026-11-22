import pytest
from backend.app.engine.sector import effective_sector,sector_message

@pytest.mark.parametrize('channel',['brand_website','brand_app','marketplace'])
def test_online_purchase(channel):
    assert effective_sector(None,{'purchase_channel':channel})=='e-commerce'
    assert sector_message(None,{'purchase_channel':channel}) is None

@pytest.mark.parametrize('sector',['banking','insurance','telecom','airlines'])
def test_regulated_sector_does_not_receive_ecommerce_rule(sector):
    assert effective_sector({'sector':sector},{'purchase_channel':'brand_app'})==sector
    assert sector_message({'sector':sector},{'purchase_channel':'brand_app'})=='Sector-specific rules not configured'

def test_unknown_channel_not_assumed():
    assert effective_sector(None,{}) is None
    assert sector_message(None,{})=='Online purchase channel needs verification'

@pytest.mark.parametrize('sector',['banking','insurance','telecom','airlines'])
def test_regulated_fact_sector_beats_conflicting_online_evidence(sector):
    assert effective_sector({'sector':'e-commerce'},{'sector':sector,'purchase_channel':'brand_website'})==sector


def test_offline_purchase_beats_ecommerce_directory():
    assert effective_sector({'sector':'e-commerce'},{'purchase_channel':'offline','online_purchase':True})=='offline'


def test_insurance_issue_beats_inferred_website():
    facts={'company_name':'Cedar Insurer','issue_summary_en':'The insurance claim is pending.','purchase_channel':'brand_website'}
    assert effective_sector(None,facts)=='insurance'


@pytest.mark.parametrize('text,channel,sector',[
 ('A purchase from an e-commerce website for order ZZ-123.','brand_website',None),
 ('I ordered groceries through an online grocery app.','brand_app',None),
 ('Insurance claim submitted to the insurer.','brand_website','insurance'),
 ('I bought this at a physical retail store.','offline',None),
])
def test_source_channel_and_sector_correct_unsupported_inference(monkeypatch,text,channel,sector):
    import asyncio
    from backend.app.ai import extract_case
    from backend.app.ai.schemas import CaseFacts,FieldConfidence
    async def fake(*args,**kwargs):
        return CaseFacts(company_name=None,order_id=None,amount_inr=None,purchase_date=None,issue_type='other',issue_summary_en='Unresolved issue',user_demand='other',events=[],contact_attempts=[],days_elapsed=None,missing_info=[],field_confidence=FieldConfidence(company_name=0,order_id=0,amount_inr=0,purchase_date=0),purchase_channel='brand_website' if sector else 'unknown')
    monkeypatch.setattr(extract_case,'call_structured',fake)
    facts=asyncio.run(extract_case.extract_case(text,[]))
    assert facts.purchase_channel==channel and facts.sector==sector


def test_known_airline_cannot_inherit_ecommerce_rules():
    assert effective_sector({'id':'indigo','sector':'travel'},{'purchase_channel':'brand_app'})=='airlines'
