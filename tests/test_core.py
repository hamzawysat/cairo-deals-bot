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


def test_message_includes_description_features_and_hashtags():
    text = message_for({
        "title": "سلك توصيل",
        "description": "للتوصيل في التجارب الإلكترونية.",
        "features": ["توصيل Female إلى Male", "للمشروعات الإلكترونية"],
        "hashtags": ["إلكترونيات", "#مشروعات"],
        "price_egp": None,
    }, "https://example.com/item")
    assert "للتوصيل في التجارب الإلكترونية." in text
    assert "• توصيل Female إلى Male" in text
    assert "#إلكترونيات" in text
    assert "https://example.com/item" in text


def test_message_shows_price_only_when_provided():
    text = message_for({
        "title": "منتج",
        "price_egp": 120,
        "original_price_egp": 150,
    }, "https://example.com")
    assert "💰 السعر: 120 جنيه" in text
    assert "🏷️ السعر السابق: 150 جنيه" in text
