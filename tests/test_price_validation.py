from src.main import message_for, offer_score


def test_message_omits_non_numeric_current_price():
    text = message_for({
        "title": "منتج",
        "price_egp": "unknown",
        "original_price_egp": 150,
    }, "https://example.com")
    assert "السعر" not in text


def test_message_omits_infinite_current_price():
    text = message_for({
        "title": "منتج",
        "price_egp": "inf",
    }, "https://example.com")
    assert "السعر" not in text


def test_invalid_price_does_not_increase_offer_score():
    assert offer_score({"title": "منتج", "price_egp": "NaN"}) == offer_score({"title": "منتج"})
