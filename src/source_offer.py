"""Source-first Amazon offer extraction with strict redirect allowlisting."""
from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urljoin, urlparse

import requests

from src.original_content import extract_egypt_price_text
from src.processor import build_amazon_affiliate_url

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
OLD_PRICE_LINE_RE = re.compile(r"السابق|قبل|السعر القديم|old price|original|\bwas\b", re.IGNORECASE)
CURRENT_PRICE_LINE_RE = re.compile(r"السعر الحالي|السعر بعد الخصم|السعر|الآن|current price|now", re.IGNORECASE)

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
    r"(?:السعر|سعر|جنيه|ج\.م|EGP|\bLE\b|ريال|ر\.س|اطلب|اشتر|الرابط|اضغط|خصم|عرض|للقطعة|عند شراء|لما تشتري|amazon\s*prime)",
    re.IGNORECASE,
)


_SOURCE_EGP_PRICE_RE = re.compile(
    # Accept grouped thousands (1,349 / 66,949) and optional decimal fractions.
    r"((?:[0-9٠-٩۰-۹]{1,3}(?:,[0-9٠-٩۰-۹]{3})+|[0-9٠-٩۰-۹]+)"
    r"(?:[.٫][0-9٠-٩۰-۹]{1,2})?)\s*"
    r"(?:جنيه(?:اً)?|جنيهات|جنية|ج\.?م\.?|EGP|L\.?E\.?|LE|ج)(?![\w])",
    re.IGNORECASE,
)
_SOCIAL_CTA_RE = re.compile(
    r"تابعنا|جميع منصات التواصل|قناتنا على|قناتنا لعروض|اضغط هنا للانضمام|"
    r"واتساب|تليجرام|تيليجرام|للانضمام|لينك العرض|رابط العرض",
    re.IGNORECASE,
)


def extract_source_price(text: str) -> tuple[str, str] | None:
    """Extract an EGP price explicitly written in the Telegram post."""
    normalized = (text or "").translate(_DIGITS)
    matches = []
    for line in normalized.splitlines():
        if OLD_PRICE_LINE_RE.search(line):
            continue
        found = list(_SOURCE_EGP_PRICE_RE.finditer(line))
        if not found:
            continue
        match = found[-1]
        amount = match.group(1).replace("٫", ".").replace(",", "")
        matches.append((0 if CURRENT_PRICE_LINE_RE.search(line) else 1, amount))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0])
    return matches[0][1] + " جنيه", "EGP"


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


def _public_dns_addresses(host: str) -> list[str]:
    """Resolve a hostname and reject private, loopback, link-local, or reserved IPs."""
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        addresses = {record[4][0] for record in records}
        if not addresses:
            return []
        for address in addresses:
            if not ipaddress.ip_address(address).is_global:
                return []
        return sorted(addresses)
    except (OSError, ValueError):
        return []


def _host_is_public(host: str, host_resolver=None) -> bool:
    try:
        addresses = (host_resolver or _public_dns_addresses)(host)
        parsed = [ipaddress.ip_address(str(address)) for address in addresses]
        return bool(parsed) and all(address.is_global for address in parsed)
    except (OSError, TypeError, ValueError):
        return False


def resolve_amazon_product_url(
    url: str, *, session: requests.Session | None = None, max_redirects: int = 8,
    diagnostics: dict | None = None, host_resolver=None,
) -> tuple[str, str] | None:
    """Resolve allowlisted HTTPS Amazon links, validating public DNS at every hop."""
    client = session or requests.Session()
    owns_session = session is None
    if owns_session:
        client.trust_env = False
    current = url
    try:
        for redirect_number in range(max_redirects + 1):
            if not is_allowed_amazon_url(current):
                if diagnostics is not None:
                    diagnostics["reason"] = "redirect_host_not_allowlisted"
                    diagnostics["host"] = (urlparse(current).hostname or "unknown").lower()
                return None
            host = (urlparse(current).hostname or "").lower()
            if not _host_is_public(host, host_resolver):
                if diagnostics is not None:
                    diagnostics["reason"] = "host_dns_not_public"
                    diagnostics["host"] = host
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
                    if redirect_number >= max_redirects:
                        if diagnostics is not None:
                            diagnostics["reason"] = "redirect_limit_exceeded"
                        return None
                    current = urljoin(current, location)
                    if diagnostics is not None:
                        diagnostics["redirect_host"] = (urlparse(current).hostname or "unknown").lower()
                    continue
                if diagnostics is not None:
                    diagnostics["final_status"] = response.status_code
                    diagnostics["final_host"] = host
                    diagnostics["final_path"] = urlparse(current).path[:100]
                if response.status_code < 200 or response.status_code >= 300:
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
    """Prefer a real product line from the post and ignore channel calls-to-action."""
    for source in (message_text or "", ocr_text or ""):
        for raw_line in source.splitlines():
            line = re.sub(r"https?://\S+", "", raw_line)
            line = re.sub(r"^[\W_]+", "", line, flags=re.UNICODE)
            line = re.sub(r"\s+", " ", line).strip(" -|")
            # Remove an explicit EGP amount when the source puts it on the title line.
            line = _SOURCE_EGP_PRICE_RE.sub("", line)
            line = re.sub(r"\b(?:بسعر|السعر|حاليًا|الآن)\b", "", line, flags=re.IGNORECASE)
            line = re.sub(r"\s+", " ", line).strip(" -|:،")
            # Remove common OCR debris and dangling price-introduction particles.
            line = re.sub(r"^\s*\d{1,2}\s*[([{]\s*بم?\s*\d+\s*", "", line)
            line = re.sub(r"(?:\s+بـ?)+$", "", line).strip(" -|:،")
            if not line or len(line) < 4 or len(line) > 120:
                continue
            if PRODUCT_NAME_SKIP.search(line) or _SOCIAL_CTA_RE.search(line):
                continue
            if re.fullmatch(r"[\d\W_]+", line):
                continue
            if _SOURCE_EGP_PRICE_RE.fullmatch(line):
                continue
            return line
    return None


def build_source_candidate(
    *, message_id: int, message_text: str, ocr_text: str = "",
    entity_urls: list[str] | None = None, tracking_id: str = "cairodeals-21",
    source_channel: str = "@OffersEgyptofficial", resolver=resolve_amazon_product_url,
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
    return {
        "source_channel": source_channel,
        "source_message_id": int(message_id),
        "product_name_source": name,
        "asin": asin,
        "advertised_price": price,
        "currency": currency,
        "price_source": "source_message_explicit_currency",
        "affiliate_url": affiliate_url,
        "caption_preview": (
            f"✨ عرض جديد من Cairo Deals\n\n"
            f"📦 {name}\n\n"
            f"💰 السعر المعلن: {price}\n\n"
            "🛒 تفاصيل المنتج والشراء من هنا:\n"
            f"{affiliate_url}\n\n"
            "قد يتغير السعر أو التوافر لدى البائع."
        ),
        "image_status": "source_image_review_only_not_cleared_for_republication",
        "publishing_performed": False,
        "review_status": "preview_ready_requires_approved_image_and_human_review",
    }
