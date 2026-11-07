"""Source-first Amazon offer extraction with strict redirect allowlisting."""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests

from src.original_content import extract_egypt_price_text
from src.processor import build_amazon_affiliate_url

ALLOWED_HOSTS = {
    "amazon.eg", "www.amazon.eg", "m.amazon.eg",
    "amazon.com", "www.amazon.com", "m.amazon.com",
    "amzn.to", "amzn.eu", "a.co", "link.amazon",
}
URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")
PRODUCT_NAME_SKIP = re.compile(
    r"(?:السعر|جنيه|ج\.م|EGP|\bLE\b|ريال|ر\.س|اطلب|اشتر|الرابط|اضغط|خصم|عرض|amazon\s*prime)",
    re.IGNORECASE,
)


def is_allowed_amazon_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme == "https"
            and (parsed.hostname or "").lower() in ALLOWED_HOSTS
            and parsed.port in (None, 443)
            and not parsed.username
            and not parsed.password
        )
    except ValueError:
        return False


def extract_urls(text: str, entity_urls: list[str] | None = None) -> list[str]:
    found = []
    for raw in URL_RE.findall(text or "") + (entity_urls or []):
        url = raw.strip().rstrip(".,);]}>")
        if url not in found:
            found.append(url)
    return found


def resolve_amazon_product_url(
    url: str, *, session: requests.Session | None = None, max_redirects: int = 8
) -> tuple[str, str] | None:
    """Resolve only HTTPS Amazon-owned links; reject every off-domain redirect."""
    client = session or requests.Session()
    owns_session = session is None
    if owns_session:
        client.trust_env = False
    current = url
    try:
        for _ in range(max_redirects + 1):
            if not is_allowed_amazon_url(current):
                return None
            response = client.get(
                current, allow_redirects=False, timeout=(5, 12),
                headers={"User-Agent": "CairoDealsPreview/1.0"},
                stream=True,
            )
            try:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("Location")
                    if not location:
                        return None
                    current = urljoin(current, location)
                    continue
                if response.status_code < 200 or response.status_code >= 400:
                    return None
                parsed = urlparse(current)
                parts = [part for part in parsed.path.split("/") if part]
                asin = None
                for index, part in enumerate(parts[:-1]):
                    if part.lower() in {"dp", "product"} and ASIN_RE.fullmatch(parts[index + 1].upper()):
                        asin = parts[index + 1].upper()
                        break
                if asin is None:
                    match = re.search(r"/gp/aw/d/([A-Z0-9]{10})(?:/|$)", parsed.path, re.I)
                    if match:
                        asin = match.group(1).upper()
                if asin is None:
                    return None
                return asin, f"https://www.amazon.eg/dp/{asin}"
            finally:
                response.close()
        return None
    except requests.RequestException:
        return None
    finally:
        if owns_session:
            client.close()


def extract_product_name(message_text: str, ocr_text: str = "") -> str | None:
    """Take a descriptive source line; never invent a product identity."""
    candidates = []
    for line in ((message_text or "") + "\n" + (ocr_text or "")).splitlines():
        line = re.sub(r"https?://\S+", "", line)
        line = re.sub(r"^[\W_]+", "", line, flags=re.UNICODE)
        line = re.sub(r"\s+", " ", line).strip(" -|")
        if not line or len(line) < 4 or len(line) > 120:
            continue
        if PRODUCT_NAME_SKIP.search(line):
            continue
        if re.fullmatch(r"[\d\W_]+", line):
            continue
        if line not in candidates:
            candidates.append(line)
    return candidates[0] if candidates else None


def build_source_candidate(
    *, message_id: int, message_text: str, ocr_text: str = "",
    entity_urls: list[str] | None = None, tracking_id: str = "cairodeals-21",
    resolver=resolve_amazon_product_url,
) -> dict | None:
    """Build a non-publishing preview only when name, ASIN, and explicit EGP price exist."""
    urls = extract_urls(message_text, entity_urls)
    resolved = []
    for url in urls:
        result = resolver(url)
        if result and result not in resolved:
            resolved.append(result)
    asins = {item[0] for item in resolved}
    if len(asins) != 1:
        return None
    asin = next(iter(asins))
    combined = "\n".join(part for part in (message_text, ocr_text) if part)
    price = extract_egypt_price_text(combined)
    name = extract_product_name(message_text, ocr_text)
    if not name or not price:
        return None
    affiliate_url = build_amazon_affiliate_url(asin, tracking_id)
    return {
        "source_channel": "@amzon44",
        "source_message_id": int(message_id),
        "product_name_source": name,
        "asin": asin,
        "advertised_price": price,
        "price_source": "message_or_ocr_explicit_egp",
        "affiliate_url": affiliate_url,
        "caption_preview": (
            f"🛍️ تفاصيل العرض\n{name}\n\n💰 السعر المعلن: {price}\n"
            "🔎 راجع تفاصيل المنتج والسعر الحالي من صفحة البيع الرسمية.\n\n"
            f"🔗 {affiliate_url}"
        ),
        "image_status": "source_image_review_only_not_cleared_for_republication",
        "publishing_performed": False,
        "review_status": "preview_ready_requires_image_rights_and_human_review",
    }
