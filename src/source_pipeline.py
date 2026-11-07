"""Prepare safe, original Arabic offer previews from verified product facts."""
from __future__ import annotations

from src.original_content import build_original_caption
from src.processor import build_amazon_affiliate_url


def prepare_verified_offer_preview(
    product_name: str,
    price_text: str,
    asin: str,
    tracking_id: str,
    source_text: str = "",
) -> dict[str, str] | None:
    """Return a preview only when caller-supplied facts are independently verified.

    This function validates formats and creates the Egypt affiliate URL. It does
    not verify product identity, price, stock, or image rights. OCR text alone
    must never be passed as verified facts.
    """
    try:
        normalized_asin = (asin or "").strip().upper()
        affiliate_url = build_amazon_affiliate_url(normalized_asin, tracking_id)
    except (TypeError, ValueError):
        return None

    caption = build_original_caption(
        product_name=product_name,
        price_text=price_text,
        affiliate_url=affiliate_url,
        source_text=source_text,
    )
    if caption is None:
        return None

    return {
        "asin": normalized_asin,
        "affiliate_url": affiliate_url,
        "caption": caption,
    }
