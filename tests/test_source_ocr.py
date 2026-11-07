"""Safety classification tests for source-channel OCR candidates."""
from scripts.inspect_source_samples import classify_ocr_sample


def test_rejects_prime_subscription_in_foreign_currency():
    status, reason = classify_ocr_sample([
        "امازون برايم",
        "الاشتراك بسعر 16 ر.س. / الشهر فقط",
    ])
    assert status == "skip_non_product_foreign_currency"
    assert "foreign currency" in reason


def test_rejects_foreign_currency_even_for_product_photo():
    status, reason = classify_ocr_sample([
        "Wrigley's Extra Blueberry",
        "السعر 20 ر.س.",
    ])
    assert status == "skip_foreign_currency"
    assert "Egypt price" in reason


def test_product_brand_still_requires_manual_verification():
    status, reason = classify_ocr_sample([
        "WRIGLEY'S",
        "EXTRA BLUEBERRY FLAVOUR",
    ])
    assert status == "manual_product_verification"
    assert "ASIN" in reason
