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
