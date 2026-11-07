"""Build buyer-facing Arabic captions from verified product facts only."""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlparse

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_AMOUNT = r"([0-9]+(?:[.,٫][0-9]{1,2})?)"
# "ج" is accepted only as a trailing Egyptian-pound abbreviation; SAR is never converted.
_CURRENCY = r"(?:جنيه(?:اً)?|جنيهات|ج\.?م\.?|EGP|L\.?E\.?|LE|ج(?=\s|$|[،,.]))"
PRICE_RE = re.compile(r"^\d+(?:[.]\d{1,2})?\s*جنيه$")
PRICE_WITH_SUFFIX_RE = re.compile(_AMOUNT + r"\s*" + _CURRENCY, re.IGNORECASE)
PRICE_WITH_PREFIX_RE = re.compile(_CURRENCY + r"\s*" + _AMOUNT, re.IGNORECASE)
OLD_PRICE_RE = re.compile(r"قبل|بدلاً? من|كان السعر|السعر القديم|original|was", re.IGNORECASE)
CURRENT_PRICE_RE = re.compile(r"السعر|بعد الخصم|الآن|حالي[اًا]|عرض", re.IGNORECASE)
ASIN_PATH_RE = re.compile(r"^/dp/([A-Z0-9]{10})/?$", re.IGNORECASE)


def extract_egypt_price_text(text: str) -> str | None:
    """Extract an explicitly EGP-denominated offer price from ad/OCR text."""
    candidates: list[tuple[int, int, str]] = []
    for index, raw_line in enumerate((text or "").translate(_DIGITS).splitlines()):
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line or OLD_PRICE_RE.search(line):
            continue
        match = PRICE_WITH_SUFFIX_RE.search(line)
        amount = match.group(1) if match else None
        if amount is None:
            match = PRICE_WITH_PREFIX_RE.search(line)
            amount = match.group(1) if match else None
        if amount is None:
            continue
        amount = amount.replace("٫", ".").replace(",", ".")
        priority = 0 if CURRENT_PRICE_RE.search(line) else 1
        candidates.append((priority, index, f"{amount} جنيه"))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def normalize_egypt_price_text(value: str) -> str | None:
    """Normalize a standalone price or a price copied with its ad label."""
    raw = (value or "").translate(_DIGITS).strip()
    if PRICE_RE.fullmatch(raw):
        return raw
    return extract_egypt_price_text(raw)


def build_original_caption(
    product_name: str,
    price_text: str,
    affiliate_url: str,
    source_text: str = "",
) -> str | None:
    """Build a fresh caption; source editorial wording is never reused.

    Product name and price must already be verified. Price may be supplied
    directly or extracted from source post/OCR text; its Egyptian currency
    marker must be explicit. OCR alone does not verify product identity.
    """
    name = re.sub(r"\s+", " ", (product_name or "")).strip()
    price = normalize_egypt_price_text(price_text)
    if not name or len(name) > 120 or "\n" in name or not price:
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
