import json
from src.main import message_for
from src.providers import build_affiliate_url, ProviderError

def test_amazon_link_contains_tracking_id():
    url = build_affiliate_url({"store":"amazon_eg","title":"دفاية","search_terms":"دفاية"}, {"tracking_id":"cairodeals-21"})
    assert "cairodeals-21" in url
    assert url.startswith("https://www.amazon.eg/")

def test_jumia_needs_verified_affiliate_url():
    try:
        build_affiliate_url({"store":"jumia_eg","title":"منتج"}, {})
        assert False, "Expected ProviderError"
    except ProviderError:
        pass

def test_message_does_not_invent_price():
    text = message_for({"title":"منتج","price_egp":None}, "https://example.com")
    assert "السعر" not in text
    assert "https://example.com" in text
