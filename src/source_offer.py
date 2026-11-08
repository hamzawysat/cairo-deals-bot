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
ALLOWED_HOSTS = {"amazon.eg","www.amazon.eg","m.amazon.eg","amazon.com","www.amazon.com","m.amazon.com","amazon.sa","www.amazon.sa","m.amazon.sa","amzn.to","amzn.eu","a.co","link.amazon","amzlinks.in","www.amzlinks.in",}
URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")
PRODUCT_NAME_SKIP = re.compile(r"(?:السعر|سعر|جنيه|ج\.م|EGP|\bLE\b|ريال|ر\.س|اطلب|اشتر|الرابط|اضغط|خصم|عرض|للقطعة|عند شراء|لما تشتري|amazon\s*prime)", re.IGNORECASE)
_SOURCE_EGP_PRICE_RE = re.compile(r"((?:[0-9٠-٩۰-۹]{1,3}(?:,[0-9٠-٩۰-۹]{3})+|[0-9٠-٩۰-۹]+)(?:[.٫][0-9٠-٩۰-۹]{1,2})?)\s*(?:جنيه(?:اً)?|جنيهات|جنية|ج\.?م\.?|EGP|L\.?E\.?|LE|ج)(?![\w])", re.IGNORECASE)
_SOCIAL_CTA_RE = re.compile(r"تابعنا|جميع منصات التواصل|قناتنا على|قناتنا لعروض|اضغط هنا للانضمام|واتساب|تليجرام|تيليجرام|للانضمام|لينك العرض|رابط العرض", re.IGNORECASE)

def extract_source_price(text: str):
    normalized = (text or "").translate(_DIGITS)
    matches = []
    for line in normalized.splitlines():
        if OLD_PRICE_LINE_RE.search(line): continue
        found = list(_SOURCE_EGP_PRICE_RE.finditer(line))
        if not found: continue
        match = found[-1]
        amount = match.group(1).replace("٫",".").replace(",","")
        matches.append((0 if CURRENT_PRICE_LINE_RE.search(line) else 1, amount))
    if not matches: return None
    matches.sort(key=lambda item: item[0])
    return matches[0][1] + " جنيه", "EGP"

def is_allowed_amazon_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme=="https" and (parsed.hostname or "").lower() in ALLOWED_HOSTS and parsed.port in (None,443) and not parsed.username and not parsed.password
    except ValueError: return False

def extract_urls(text: str, entity_urls=None):
    found=[]
    for raw in URL_RE.findall(text or "") + (entity_urls or []):
        url = raw.strip().rstrip(".,);]}>")
        if url not in found: found.append(url)
    return found

def _public_dns_addresses(host: str):
    try:
        records = socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
        addresses={r[4][0] for r in records}
        if not addresses: return []
        for a in addresses:
            if not ipaddress.ip_address(a).is_global: return []
        return sorted(addresses)
    except (OSError,ValueError): return []

def _host_is_public(host, host_resolver=None):
    try:
        addresses=(host_resolver or _public_dns_addresses)(host)
        parsed=[ipaddress.ip_address(str(a)) for a in addresses]
        return bool(parsed) and all(a.is_global for a in parsed)
    except (OSError,TypeError,ValueError): return False

def resolve_amazon_product_url(url: str, *, session=None, max_redirects: int=8, diagnostics=None, host_resolver=None):
    client = session or requests.Session()
    owns = session is None
    if owns: client.trust_env=False
    current=url
    try:
        for rn in range(max_redirects+1):
            if not is_allowed_amazon_url(current):
                if diagnostics is not None: diagnostics["reason"]="redirect_host_not_allowlisted"; diagnostics["host"]=(urlparse(current).hostname or "unknown").lower()
                return None
            host=(urlparse(current).hostname or "").lower()
            if not _host_is_public(host, host_resolver):
                if diagnostics is not None: diagnostics["reason"]="host_dns_not_public"; diagnostics["host"]=host
                return None
            response=client.get(current, allow_redirects=False, timeout=(5,12), headers={"User-Agent":"CairoDealsPreview/1.0"}, stream=True)
            try:
                if response.status_code in (301,302,303,307,308):
                    loc=response.headers.get("Location")
                    if not loc:
                        if diagnostics is not None: diagnostics["reason"]="redirect_without_location"
                        return None
                    if rn>=max_redirects:
                        if diagnostics is not None: diagnostics["reason"]="redirect_limit_exceeded"
                        return None
                    current=urljoin(current,loc); continue
                if diagnostics is not None: diagnostics["final_status"]=response.status_code; diagnostics["final_host"]=host; diagnostics["final_path"]=urlparse(current).path[:100]
                if response.status_code<200 or response.status_code>=300:
                    if diagnostics is not None: diagnostics["reason"]="http_status_rejected"
                    return None
                parsed=urlparse(current); parts=[p for p in parsed.path.split("/") if p]
                if (parsed.hostname or "").lower()=="link.amazon" and len(parts)==1 and ASIN_RE.fullmatch(parts[0].upper()):
                    asin=parts[0].upper()
                    if diagnostics is not None: diagnostics["resolved_asin"]=asin
                    return asin, f"https://www.amazon.eg/dp/{asin}"
                asin=None
                for i,part in enumerate(parts[:-1]):
                    if part.lower() in {"dp","product"} and ASIN_RE.fullmatch(parts[i+1].upper()): asin=parts[i+1].upper(); break
                if asin is None:
                    m=re.search(r"/gp/aw/d/([A-Z0-9]{10})(?:/|$)", parsed.path, re.I)
                    if m: asin=m.group(1).upper()
                if asin is None:
                    if diagnostics is not None: diagnostics["reason"]="final_url_has_no_asin"
                    return None
                if diagnostics is not None: diagnostics["resolved_asin"]=asin
                return asin, f"https://www.amazon.eg/dp/{asin}"
            finally: response.close()
        return None
    except requests.RequestException as exc:
        if diagnostics is not None: diagnostics["reason"]="request_exception"; diagnostics["error_type"]=type(exc).__name__
        return None
    finally:
        if owns: client.close()

def extract_product_name(message_text: str, ocr_text: str=""):
    for source in (message_text or "", ocr_text or ""):
        for raw_line in source.splitlines():
            line=re.sub(r"https?://\S+","",raw_line); line=re.sub(r"^[\W_]+","",line,flags=re.UNICODE); line=re.sub(r"\s+"," ",line).strip(" -|")
            line=_SOURCE_EGP_PRICE_RE.sub("",line); line=re.sub(r"\b(?:بسعر|السعر|حاليًا|الآن)\b","",line,flags=re.IGNORECASE); line=re.sub(r"\s+"," ",line).strip(" -|:،")
            line=re.sub(r"^\s*\d{1,2}\s*[([{]\s*بم?\s*\d+\s*","",line); line=re.sub(r"(?:\s+بـ?)+$","",line).strip(" -|:،")
            if not line or len(line)<4 or len(line)>120: continue
            if PRODUCT_NAME_SKIP.search(line) or _SOCIAL_CTA_RE.search(line): continue
            if re.fullmatch(r"[\d\W_]+",line): continue
            if _SOURCE_EGP_PRICE_RE.fullmatch(line): continue
            return line
    return None

def _name_for_url(message_text: str, url: str, ocr_text: str=""):
    # FIX: for combined ads like "تايد : https://link.amazon/..." take name from same line before the URL
    # Handles RTL: name is before ':' on same line, and handles URL split across lines (we join lines in preview script)
    for line in (message_text or "").splitlines():
        if url in line:
            left = line.split(url)[0]
            # take text after last newline already, strip separators
            name = left.strip().strip(":،-–—|").strip()
            # remove leading numbers / bullets
            name = re.sub(r"^[\d\.\-\*•\s]+","",name).strip()
            # remove trailing colon parts
            name = name.split(":")[ -1] if ":" in name and len(name.split(":")[-1].strip())>=2 else name
            # Actually for "تايد : " left is "تايد : " -> clean gives "تايد"
            name = re.sub(r"[:،]+$","",name).strip()
            if len(name)>=2 and len(name)<=120 and not PRODUCT_NAME_SKIP.search(name):
                return name
            break
    return extract_product_name(message_text, ocr_text)

def _make_candidate(*, message_id, message_text, ocr_text, asin, tracking_id, source_channel, name_override=None, price_override=None):
    combined="\n".join(p for p in (message_text, ocr_text) if p)
    source_price = price_override or extract_source_price(combined)
    name = name_override or extract_product_name(message_text, ocr_text)
    if not name or not source_price: return None
    price, currency = source_price
    affiliate_url = build_amazon_affiliate_url(asin, tracking_id)
    return {"source_channel":source_channel,"source_message_id":int(message_id),"product_name_source":name,"asin":asin,"advertised_price":price,"currency":currency,"price_source":"source_message_explicit_currency","affiliate_url":affiliate_url,"caption_preview":(f"✨ عرض جديد من Cairo Deals\n\n📦 {name}\n\n💰 السعر المعلن: {price}\n\n🛒 تفاصيل المنتج والشراء من هنا:\n{affiliate_url}\n\nقد يتغير السعر أو التوافر لدى البائع."),"image_status":"source_image_review_only_not_cleared_for_republication","publishing_performed":False,"review_status":"preview_ready_requires_approved_image_and_human_review",}

def build_source_candidate(*, message_id: int, message_text: str, ocr_text: str="", entity_urls=None, tracking_id: str="cairodeals-21", source_channel: str="@OffersEgyptofficial", resolver=resolve_amazon_product_url):
    # Kept for backward compat: single-product path returns None on multi-ASIN (old tests expect this)
    urls=extract_urls(message_text, entity_urls); resolved=[]
    for url in urls:
        r=resolver(url)
        if r and r not in resolved: resolved.append(r)
    asins={x[0] for x in resolved}
    if len(asins)!=1: return None
    asin=next(iter(asins))
    return _make_candidate(message_id=message_id, message_text=message_text, ocr_text=ocr_text, asin=asin, tracking_id=tracking_id, source_channel=source_channel)

def build_source_candidates(*, message_id: int, message_text: str, ocr_text: str="", entity_urls=None, tracking_id: str="cairodeals-21", source_channel: str="@OffersEgyptofficial", resolver=resolve_amazon_product_url):
    """NEW: Split a combined ad (many links in one message) into one candidate per ASIN."""
    # Fix split URLs: "https://link.amazon\n/B0..." -> join
    fixed_text = (message_text or "").replace("https://link.amazon\n", "https://link.amazon").replace("https://link.amazon \n", "https://link.amazon").replace("https://link.amazon /", "https://link.amazon/")
    # Also handle generic split: link.amazon + newline + /CODE
    fixed_text = re.sub(r"(link\.amazon)\s*\n\s*(/[A-Za-z0-9]+)", r"\1\2", fixed_text)
    urls=extract_urls(fixed_text, entity_urls); resolved=[]
    seen=set()
    for url in urls:
        r=resolver(url)
        if r and r[0] not in seen:
            seen.add(r[0]); resolved.append((url, r))
    if not resolved: return []
    # Single ASIN -> same as before
    if len(resolved)==1:
        c=_make_candidate(message_id=message_id, message_text=fixed_text, ocr_text=ocr_text, asin=resolved[0][1][0], tracking_id=tracking_id, source_channel=source_channel)
        return [c] if c else []
    # Multi ASIN -> one candidate per URL, name from its line
    out=[]
    # For combined ads, price is usually in OCR image, not text. Use combined price if available, else try per-line price, else keep candidate with price=None and let preview script fill from OCR per-product if possible
    # We still require a price: try OCR + text combined; if still None, we create candidate with placeholder and preview script will try OCR segment
    combined="\n".join(p for p in (fixed_text, ocr_text) if p)
    global_price=extract_source_price(combined)
    for url, (asin, _) in resolved:
        name=_name_for_url(fixed_text, url, ocr_text)
        # If name not found on line, fallback to generic
        if not name: name=extract_product_name(fixed_text, ocr_text) or f"منتج {asin}"
        # For multi, if global price is single value, don't assign same price to all - try to find price on same line
        line_price=None
        for line in fixed_text.splitlines():
            if url in line:
                line_price=extract_source_price(line); break
        price_to_use = line_price or global_price
        # If still no price, skip this ASIN for now (safe: don't publish wrong price) - preview will log it
        if not price_to_use: continue
        c=_make_candidate(message_id=message_id, message_text=fixed_text, ocr_text=ocr_text, asin=asin, tracking_id=tracking_id, source_channel=source_channel, name_override=name, price_override=price_to_use)
        if c:
            # Make source_message_id unique per product so pending list doesn't overwrite: suffix with asin
            c["source_message_id"]=int(message_id)
            c["source_product_key"]=f"{message_id}:{asin}"
            c["is_split_from_combined"]=True
            out.append(c)
    return out
