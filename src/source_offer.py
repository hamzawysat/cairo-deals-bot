"""Source-first Amazon offer extraction with strict redirect allowlisting."""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests

from src.original_content import extract_egypt_price_text

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
OLD_PRICE_LINE_RE = re.compile(r"السابق|قبل|السعر القديم|old price|original|\bwas\b", re.IGNORECASE)
CURRENT_PRICE_LINE_RE = re.compile(r"السعر الحالي|السعر بعد الخصم|السعر|الآن|current price|now", re.IGNORECASE)


def extract_source_price(text: str) -> tuple[str, str] | None:
    """Return only an explicitly stated Egyptian-pound price; reject all other currencies."""
    egp = extract_egypt_price_text(text or "")
    if not egp:
        return None
    return egp, "EGP"

from src.processor import build_amazon_affiliate_url

ALLOWED_HOSTS = {
    "amazon.eg", "www.amazon.eg", "m.amazon.eg",
    "amazon.com", "www.amazon.com", "m.amazon.com",
    "amazon.sa", "www.amazon.sa", "m.amazon.sa",
    "amzn.to", "amzn.eu", "a.co", "link.amazon",
    "amzlinks.in", "www.amzlinks.in",
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
    url: str, *, session: requests.Session | None = None, max_redirects: int = 8,
    diagnostics: dict | None = None,
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
                if diagnostics is not None:
                    diagnostics["reason"] = "redirect_host_not_allowlisted"
                    diagnostics["host"] = (urlparse(current).hostname or "unknown").lower()
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
                        if diagnostics is not None:
                            diagnostics["reason"] = "redirect_without_location"
                        return None
                    current = urljoin(current, location)
                    if diagnostics is not None:
                        diagnostics["redirect_host"] = (urlparse(current).hostname or "unknown").lower()
                    continue
                if diagnostics is not None:
                    diagnostics["final_status"] = response.status_code
                    diagnostics["final_host"] = (urlparse(current).hostname or "unknown").lower()
                    diagnostics["final_path"] = urlparse(current).path[:100]
                if response.status_code < 200 or response.status_code >= 400:
                    if diagnostics is not None:
                        diagnostics["reason"] = "http_status_rejected"
                    return None
                parsed = urlparse(current)
                parts = [part for part in parsed.path.split("/") if part]
                if (parsed.hostname or "").lower() == "link.amazon" and len(parts) == 1 and ASIN_RE.fullmatch(parts[0].upper()):
                    asin = parts[0].upper()
                    return asin, f"https://www.amazon.eg/dp/{asin}"
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
                    if diagnostics is not None:
                        diagnostics["reason"] = "final_url_has_no_asin"
                    return None
                if diagnostics is not None:
                    diagnostics["resolved_asin"] = asin
                return asin, f"https://www.amazon.eg/dp/{asin}"
            finally:
                response.close()
        return None
    except requests.RequestException as exc:
        if diagnostics is not None:
            diagnostics["reason"] = "request_exception"
            diagnostics["error_type"] = type(exc).__name__
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
    """Build a non-publishing preview from a source price with explicit currency."""
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
    source_price = extract_source_price(combined)
    name = extract_product_name(message_text, ocr_text)
    if not name or not source_price:
        return None
    price, currency = source_price
    affiliate_url = build_amazon_affiliate_url(asin, tracking_id)
    price_line = (
        f"💰 السعر المعلن: {price}"
        if currency == "EGP"
        else f"💰 السعر المذكور في إعلان المصدر: {price}\n⚠️ السعر بالريال السعودي ولم يتم تحويله للجنيه المصري."
    )
    return {
        "source_channel": "@amzon44",
        "source_message_id": int(message_id),
        "product_name_source": name,
        "asin": asin,
        "advertised_price": price,
        "currency": currency,
        "price_source": "message_or_ocr_explicit_currency",
        "affiliate_url": affiliate_url,
        "caption_preview": (
            f"🛍️ تفاصيل العرض\\n{name}\\n\\n{price_line}\\n"
            "🔎 راجع تفاصيل المنتج والسعر الحالي من صفحة البيع الرسمية.\\n\\n"
            f"🔗 {affiliate_url}"
        ),
        "image_status": "source_image_review_only_not_cleared_for_republication",
        "publishing_performed": False,
        "review_status": (
            "preview_ready_requires_image_rights_and_human_review"
            if currency == "EGP"
            else "preview_ready_but_sar_currency_decision_required_before_egyptian_publication"
        ),
    }
