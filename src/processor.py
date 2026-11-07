"""Safe parsing and Arabic repost formatting for Telegram source posts."""
from __future__ import annotations

import re
from urllib.parse import urlparse

ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")
URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
AMAZON_HOSTS = {
    "amazon.eg", "www.amazon.eg", "amazon.com", "www.amazon.com",
    "amzn.to", "amzn.eu", "link.amazon",
}


def extract_asin_from_url(url: str) -> str | None:
    """Extract an ASIN only from recognized Amazon domains and product paths."""
    try:
        parsed = urlparse(url.strip().rstrip(".,);]"))
    except ValueError:
        return None
    if (parsed.hostname or "").lower() not in AMAZON_HOSTS:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    for index, part in enumerate(parts[:-1]):
        if part.lower() in {"dp", "product"}:
            candidate = parts[index + 1].upper()
            if ASIN_RE.fullmatch(candidate):
                return candidate
    # Amazon mobile product path: /gp/aw/d/ASIN
    for index in range(len(parts) - 3):
        if [p.lower() for p in parts[index:index + 3]] == ["gp", "aw", "d"]:
            candidate = parts[index + 3].upper()
            if ASIN_RE.fullmatch(candidate):
                return candidate
    return None


def extract_single_asin(text: str) -> str | None:
    found = {
        asin for url in URL_RE.findall(text or "")
        if (asin := extract_asin_from_url(url)) is not None
    }
    return next(iter(found)) if len(found) == 1 else None


def build_amazon_affiliate_url(asin: str, tracking_id: str) -> str:
    asin = (asin or "").upper().strip()
    tracking_id = (tracking_id or "").strip()
    if not ASIN_RE.fullmatch(asin):
        raise ValueError("A valid Amazon ASIN is required")
    if not tracking_id or not re.fullmatch(r"[A-Za-z0-9-]+", tracking_id):
        raise ValueError("A valid Amazon tracking ID is required")
    return f"https://www.amazon.eg/dp/{asin}?tag={tracking_id}"


def format_repost(text: str, tracking_id: str) -> tuple[str, str, str] | None:
    """Return (asin, affiliate_url, Arabic caption); never invent product facts."""
    asin = extract_single_asin(text)
    if not asin:
        return None
    affiliate_url = build_amazon_affiliate_url(asin, tracking_id)
    caption = URL_RE.sub("", text or "")
    caption = re.sub(r"[ \t]{2,}", " ", caption)
    caption = re.sub(r"\n{3,}", "\n\n", caption).strip()
    caption = f"🛍️ {caption}" if caption else "🛍️ عرض جديد"
    return asin, affiliate_url, f"{caption}\n\n🔗 {affiliate_url}"
