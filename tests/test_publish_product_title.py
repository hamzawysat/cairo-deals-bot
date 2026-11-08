"""Regression tests for generic Amazon page titles."""

from scripts.publish_pending_source_offers import _choose_product_title


def test_generic_amazon_title_falls_back_to_source_product_name():
    assert _choose_product_title("لمبة LED حمراء 5 ملم", "Amazon") == "لمبة LED حمراء 5 ملم"


def test_amazon_eg_storefront_title_falls_back_to_source_product_name():
    assert _choose_product_title("مج سيراميك", "Amazon.eg") == "مج سيراميك"


def test_real_amazon_product_title_is_preferred():
    assert _choose_product_title("اسم من المصدر", "Wireless Jumper Wires") == "Wireless Jumper Wires"


def test_missing_live_title_uses_source_product_name():
    assert _choose_product_title("اسم المنتج من المصدر", "") == "اسم المنتج من المصدر"
