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



def test_nan_and_infinite_original_prices_are_not_discounts():
    from src.main import _has_real_discount
    assert not _has_real_discount("nan", 100)
    assert not _has_real_discount("inf", 100)
    assert not _has_real_discount(150, "nan")


def test_egyptian_price_short_abbreviation_is_recognized():
    from src.original_content import extract_egypt_price_text
    assert extract_egypt_price_text("دواسة حمام بسعر 150 ج") == "150 جنيه"
    assert extract_egypt_price_text("دفاية بسعر 291ج") == "291 جنيه"


def test_saudi_riyal_is_never_treated_as_egyptian_pound():
    from src.original_content import extract_egypt_price_text
    assert extract_egypt_price_text("السعر 150 ريال سعودي") is None
