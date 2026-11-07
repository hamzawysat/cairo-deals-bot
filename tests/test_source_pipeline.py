"""Tests for the verified-facts to original-caption preview pipeline."""
from src.source_pipeline import prepare_verified_offer_preview


def test_preview_builds_egypt_tagged_link_and_original_arabic_copy():
    result = prepare_verified_offer_preview(
        product_name="لمبات ليد حمراء 5 ملم - 5 قطع",
        price_text="10.80 جنيه",
        asin="B049WGppS1",
        tracking_id="cairodeals-21",
        source_text="عرض سريع بسعر خاص لفترة محدودة",
    )
    assert result is not None
    assert result["asin"] == "B049WGPP S1".replace(" ", "")
    assert result["affiliate_url"] == "https://www.amazon.eg/dp/B049WGPP S1?tag=cairodeals-21".replace(" ", "")
    assert "10.80 جنيه" in result["caption"]
    assert result["affiliate_url"] in result["caption"]


def test_preview_rejects_unverified_asin_or_price_format():
    assert prepare_verified_offer_preview(
        "منتج", "10 جنيه", "not-an-asin", "cairodeals-21"
    ) is None
    assert prepare_verified_offer_preview(
        "منتج", "السعر غير معروف", "B049WGppS1", "cairodeals-21"
    ) is None


def test_preview_rejects_caption_that_is_too_similar_to_source():
    source = "تفاصيل المنتج والسعر المعلن والعرض الحالي متاح الآن للشراء من صفحة البيع الرسمية"
    assert prepare_verified_offer_preview(
        product_name="تفاصيل المنتج والسعر المعلن والعرض الحالي متاح الآن",
        price_text="10 جنيه",
        asin="B049WGppS1",
        tracking_id="cairodeals-21",
        source_text=source,
    ) is None
