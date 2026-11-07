"""Build buyer-facing Arabic captions from verified product facts only."""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlparse

PRICE_RE = re.compile(r"^\d+(?:[.,]\d{1,2})?\s*جنيه$")
ASIN_PATH_RE = re.compile(r"^/dp/([A-Z0-9]{10})/?$", re.IGNORECASE)


def build_original_caption(
    product_name: str,
    price_text: str,
    affiliate_url: str,
    source_text: str = "",
) -> str | None:
    """Build a fresh caption; source editorial wording is never reused.

    Product name and price must already be independently verified. OCR output
    alone is not sufficient verification. Returns None when required facts
    or the canonical tagged Amazon Egypt URL are missing.
    """
    name = re.sub(r"\s+", " ", (product_name or "")).strip()
    price = re.sub(r"\s+", " ", (price_text or "")).strip()
    if not name or len(name) > 120 or "\n" in name:
        return None
    if not PRICE_RE.fullmatch(price):
        return None

    try:
        parsed = urlparse((affiliate_url or "").strip())
    except ValueError:
        return None
    match = ASIN_PATH_RE.fullmatch(parsed.path)
    tags = [value for key, value in parse_qsl(parsed.query) if key == "tag"]
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.amazon.eg"
        or not match
        or len(tags) != 1
        or not re.fullmatch(r"[A-Za-z0-9-]+", tags[0])
    ):
        return None

    # Do not paraphrase or reuse source copy. Only verified product facts enter.
    caption = (
        f"🛍️ تفاصيل العرض\n"
        f"{name}\n\n"
        f"💰 السعر المعلن: {price}\n"
        f"🔎 راجع تفاصيل المنتج والسعر الحالي من صفحة البيع الرسمية.\n\n"
        f"🔗 {affiliate_url.strip()}"
    )
    source = re.sub(r"https?://\S+", "", source_text or "")
    source = re.sub(r"\s+", " ", source).strip()
    generated = re.sub(r"\s+", " ", caption.rsplit("🔗", 1)[0]).strip()
    if len(source) >= 40 and SequenceMatcher(None, generated, source).ratio() >= 0.72:
        return None
    return caption
