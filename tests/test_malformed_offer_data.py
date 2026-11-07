from src.main import message_for


def test_message_ignores_invalid_original_price():
    text = message_for({
        "title": "منتج",
        "price_egp": 100,
        "original_price_egp": "not-a-number",
    }, "https://example.com")
    assert "💰 100 جنيه" in text
    assert "السعر السابق" not in text


def test_message_ignores_original_price_when_current_price_missing():
    text = message_for({
        "title": "منتج",
        "price_egp": None,
        "original_price_egp": "150",
    }, "https://example.com")
    assert "السعر" not in text
