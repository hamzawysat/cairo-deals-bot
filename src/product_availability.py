"""Conservative Amazon Egypt product-availability checks for short affiliate links."""
import json
import re
from urllib.parse import urlparse

import requests

AVAILABLE = "AVAILABLE"
UNAVAILABLE = "UNAVAILABLE"
UNKNOWN = "UNKNOWN"

_ASIN_RE = re.compile(r"/(?:dp|gp/product|product)/([A-Z0-9]{10})(?:[/?]|$)", re.I)
_UNAVAILABLE_MARKERS = (
    "currently unavailable",
    "temporarily out of stock",
    "out of stock",
    "currently out of stock",
    "غير متوفر",
    "نفد من المخزون",
)
_AVAILABLE_MARKERS = (
    "in stock",
    "متوفر",
    "متوفر في المخزون",
)


def _jsonld_availability(value):
    """Find schema.org availability values in nested JSON-LD objects."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() == "availability" and isinstance(item, str):
                normalized = item.lower()
                if any(word in normalized for word in ("outofstock", "soldout", "discontinued")):
                    return UNAVAILABLE
                if any(word in normalized for word in ("instock", "limitedavailability", "onlineonly")):
                    return AVAILABLE
            found = _jsonld_availability(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _jsonld_availability(item)
            if found:
                return found
    return None


def classify_amazon_product_page(html):
    """Classify only explicit availability signals; ambiguous pages stay UNKNOWN."""
    scripts = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html or "",
        flags=re.I | re.S,
    )
    for raw in scripts:
        try:
            result = _jsonld_availability(json.loads(raw.strip()))
        except (ValueError, TypeError):
            result = None
        if result:
            return result

    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"\s+", " ", text).lower()
    if any(marker in text for marker in _UNAVAILABLE_MARKERS):
        return UNAVAILABLE
    if any(marker in text for marker in _AVAILABLE_MARKERS):
        return AVAILABLE
    return UNKNOWN


def check_amazon_offer_availability(offer, session=None):
    """Resolve a short affiliate URL and inspect Amazon EG's explicit stock signal.

    Returns (status, detail). The original affiliate URL is never modified.
    """
    affiliate_url = str(offer.get("affiliate_url") or "").strip()
    if offer.get("store") != "amazon_eg":
        return AVAILABLE, "availability check not required for this store"
    if not affiliate_url.startswith("https://"):
        return UNKNOWN, "missing HTTPS affiliate URL"

    http = session or requests
    try:
        response = http.get(
            affiliate_url,
            allow_redirects=True,
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; CairoDealsBot/1.0)",
                "Accept-Language": "ar-EG,ar;q=0.9,en;q=0.8",
            },
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return UNKNOWN, f"could not resolve/check Amazon link: {exc.__class__.__name__}"

    final = urlparse(getattr(response, "url", "") or "")
    if final.hostname not in {"amazon.eg", "www.amazon.eg"}:
        return UNKNOWN, "short link did not resolve to an Amazon Egypt product page"
    if not _ASIN_RE.search(final.path):
        return UNKNOWN, "resolved Amazon URL does not contain a recognizable product ASIN"

    status = classify_amazon_product_page(getattr(response, "text", ""))
    return status, f"Amazon product page checked (ASIN {_ASIN_RE.search(final.path).group(1)})"
