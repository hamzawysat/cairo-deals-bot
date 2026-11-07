"""Prepare safe, original Arabic offer previews from verified product facts."""
from __future__ import annotations

from src.original_content import (
    build_original_caption,
    extract_egypt_price_text,
    normalize_egypt_price_text,
)
from src.processor import build_amazon_affiliate_url


def prepare_verified_offer_preview(
    product_name: str,
    price_text: str = "",
    asin: str = "",
    tracking_id: str = "",
    source_text: str = "",
) -> dict[str, str] | None:
    """Build a preview using the price stated in the source post or OCR.

    The Amazon URL is used only to identify/link the product through its ASIN;
    it is never used as the source of the advertised price. The caller must
    independently verify product identity and ASIN. An explicitly EGP-labelled
    price may be passed directly or extracted from source_text (including OCR).
    """
    try:
        normalized_asin = (asin or "").strip().upper()
        affiliate_url = build_amazon_affiliate_url(normalized_asin, tracking_id)
    except (TypeError, ValueError):
        return None

    advertised_price = normalize_egypt_price_text(price_text)
    if advertised_price is None:
        advertised_price = extract_egypt_price_text(source_text)
    if advertised_price is None:
        return None

    caption = build_original_caption(
        product_name=product_name,
        price_text=advertised_price,
        affiliate_url=affiliate_url,
        source_text=source_text,
    )
    if caption is None:
        return None

    return {
        "asin": normalized_asin,
        "advertised_price": advertised_price,
        "affiliate_url": affiliate_url,
        "caption": caption,
    }
