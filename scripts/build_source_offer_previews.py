#!/usr/bin/env python3
"""Read source Telegram posts and build non-publishing, review-only offer previews."""
from __future__ import annotations
import asyncio, json, logging, os, re, sys, tempfile, time
from pathlib import Path
from PIL import Image, ImageEnhance, ImageOps
import pytesseract
from telethon import TelegramClient
from telethon.sessions import StringSession
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.source_offer import build_source_candidate, build_source_candidates, extract_product_name, extract_urls, resolve_amazon_product_url
from src.source_publish import telegram_published_asins
from src.original_content import extract_egypt_price_text
from urllib.parse import urlparse
SOURCE_CHANNEL = os.environ.get("SOURCE_TELEGRAM_CHANNEL", "@OffersEgyptofficial")
POST_LIMIT = 30
PHOTO_LIMIT = 30
TRACKING_ID = "cairodeals-21"

def image_ocr(path: str) -> str:
    """Run two complementary OCR layouts on one enhanced grayscale image."""
    with Image.open(path) as source:
        image = source.convert("RGB")
        # Avoid expensive upscaling of small source images. Tesseract handles
        # native-resolution images directly; only shrink oversized images.
        max_dimension = 1200
        if max(image.size) > max_dimension:
            factor = max_dimension / max(image.size)
            image = image.resize(
                (max(1, int(image.width * factor)), max(1, int(image.height * factor))),
                Image.Resampling.LANCZOS,
            )
        gray = ImageOps.autocontrast(ImageOps.grayscale(image))
        enhanced = ImageEnhance.Contrast(gray).enhance(1.5)
        primary = pytesseract.image_to_string(
            enhanced, lang="ara+eng", config="--oem 1 --psm 6"
        )
        # Run sparse-text OCR only when the first pass did not recover
        # both a product name and an explicit Egyptian-pound price.
        if extract_product_name(primary) and extract_egypt_price_text(primary):
            return primary
        fallback = pytesseract.image_to_string(
            enhanced, lang="ara+eng", config="--oem 1 --psm 11"
        )
        return "\n".join(part for part in (primary, fallback) if part)


def remember_ocr_text(cache: dict, message_id: int, text: str, limit: int = 120) -> None:
    """Keep a bounded, insertion-ordered OCR cache keyed by source message ID."""
    cache[str(message_id)] = text
    while len(cache) > limit:
        cache.pop(next(iter(cache)))


def cached_ocr_text(cache: dict, message_id: int):
    """Return cached OCR text, including an intentionally cached empty result."""
    return cache.get(str(message_id))


def filter_pending_candidates(pending: list[dict], state: dict) -> list[dict]:
    """Deduplicate queued ASINs but retain Telegram-success/ Facebook-pending retries."""
    published_asins = telegram_published_asins(state)
    kept = []
    seen_asins = set()
    statuses = state.get("platform_status", {})
    for candidate in pending:
        if not isinstance(candidate, dict):
            continue
        asin = str(candidate.get("asin") or "").strip().upper()
        status = statuses.get(str(candidate.get("source_message_id", "")), {})
        facebook_retry = bool(status.get("telegram") and not status.get("facebook"))
        if not asin or asin in seen_asins or (asin in published_asins and not facebook_retry):
            continue
        kept.append(candidate)
        seen_asins.add(asin)
    return kept

def merge_preview_state(
    prior_state: dict,
    *,
    last_seen_message_id: int,
    pending_candidates: list[dict],
    ocr_cache: dict,
) -> dict:
    """Update preview-owned fields without dropping publisher-owned state."""
    updated = dict(prior_state)
    updated.update({
        "last_seen_message_id": last_seen_message_id,
        "published_message_ids": prior_state.get("published_message_ids", []),
        "platform_status": prior_state.get("platform_status", {}),
        "published_asins": sorted(telegram_published_asins(prior_state)),
        "pending_candidates": pending_candidates,
        "ocr_cache": ocr_cache,
    })
    return updated

async def run() -> bool:
    raw_id=os.environ.get("TELEGRAM_API_ID",""); api_hash=os.environ.get("TELEGRAM_API_HASH",""); session=os.environ.get("TELEGRAM_SESSION","")
    if not raw_id.isdigit() or not api_hash or not session:
        print("PREVIEW FAILED: Telegram secrets are missing."); return False
    client=TelegramClient(StringSession(session), int(raw_id), api_hash)
    candidates=[]; seen_messages=set(); state_path=Path("artifacts/source-offer-state.json")
    try: prior_state=json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    except (OSError, ValueError): prior_state={}
    prior_message_ids={int(v) for v in prior_state.get("published_message_ids",[])}
    ocr_cache = {
        str(k): str(v)
        for k, v in (prior_state.get("ocr_cache", {}) or {}).items()
        if str(k).isdigit() and isinstance(v, str)
    }
    ocr_cache_hits = 0
    ocr_cache_entries_loaded = len(ocr_cache)
    media_download_seconds = 0.0
    ocr_seconds = 0.0
    link_resolution_seconds = 0.0
    already_published_asins = telegram_published_asins(prior_state)
    pending_candidates = filter_pending_candidates(
        prior_state.get("pending_candidates", []), prior_state
    )
    pending_seen_asins = {
        str(item.get("asin") or "").strip().upper() for item in pending_candidates
    }
    pending_message_ids={int(i.get("source_message_id",0)) for i in pending_candidates if isinstance(i,dict)}
    pending_keys={str(i.get("source_product_key", i.get("source_message_id"))) for i in pending_candidates if isinstance(i,dict)}
    last_seen_message_id=int(prior_state.get("last_seen_message_id",0) or 0)
    highest_seen_message_id=last_seen_message_id; duplicate_skipped=0
    rejected={"no_resolved_asin_or_ambiguous":0,"missing_name_or_egp_price":0,"photo_ocr_failed":0}
    rejection_details=[]; photo_count=0
    try:
        await asyncio.wait_for(client.connect(), timeout=25)
        if not await client.is_user_authorized():
            print("PREVIEW FAILED: Telegram session is not authorized."); return False
        source=await asyncio.wait_for(client.get_entity(SOURCE_CHANNEL), timeout=20)
        with tempfile.TemporaryDirectory(prefix="cairo-source-preview-") as temp_dir:
            async for message in client.iter_messages(source, limit=POST_LIMIT):
                if message.id in seen_messages: continue
                seen_messages.add(message.id)
                highest_seen_message_id=max(highest_seen_message_id, int(message.id))
                if int(message.id) <= last_seen_message_id: continue
                body=message.message or ""
                entity_urls=[e.url for e in (message.entities or []) if getattr(e,"url",None)]
                ocr_text=""
                # Prefer the post text; OCR is unnecessary when both required
                # facts are already present in the caption.
                body_has_name = bool(extract_product_name(body))
                body_has_egp_price = bool(extract_egypt_price_text(body))
                if message.photo and not (body_has_name and body_has_egp_price):
                    cached_text = cached_ocr_text(ocr_cache, message.id)
                    if cached_text is not None:
                        ocr_text = cached_text
                        ocr_cache_hits += 1
                    elif photo_count < PHOTO_LIMIT:
                        photo_count += 1
                        try:
                            path=str(Path(temp_dir)/f"source_{message.id}.jpg")
                            download_started = time.perf_counter()
                            downloaded=await asyncio.wait_for(client.download_media(message, file=path), timeout=30)
                            media_download_seconds += time.perf_counter() - download_started
                            if downloaded and Path(downloaded).is_file():
                                ocr_started = time.perf_counter()
                                ocr_text=image_ocr(downloaded)
                                ocr_seconds += time.perf_counter() - ocr_started
                                remember_ocr_text(ocr_cache, message.id, ocr_text)
                        except Exception:
                            rejected["photo_ocr_failed"]+=1
                urls=extract_urls(body, entity_urls)
                resolution_cache={}; resolution_diagnostics={}
                def cached_resolver(url):
                    if url not in resolution_cache:
                        details={}; resolution_cache[url]=resolve_amazon_product_url(url, diagnostics=details); resolution_diagnostics[url]=details
                    return resolution_cache[url]
                # ===== FIXED PART: split combined ads instead of rejecting them =====
                try:
                    resolution_started = time.perf_counter()
                    candidates_for_message=build_source_candidates(message_id=message.id, message_text=body, ocr_text=ocr_text, entity_urls=entity_urls, tracking_id=TRACKING_ID, source_channel=SOURCE_CHANNEL, resolver=cached_resolver)
                    link_resolution_seconds += time.perf_counter() - resolution_started
                except Exception:
                    link_resolution_seconds += time.perf_counter() - resolution_started
                    candidates_for_message=[]
                if not candidates_for_message:
                    combined_text=body+"\n"+ocr_text
                    resolved_asins=sorted({v[0] for v in resolution_cache.values() if v})
                    name_candidate=extract_product_name(body, ocr_text)
                    price_candidate=extract_egypt_price_text(combined_text)
                    if not urls or not resolved_asins: reason="no_resolved_amazon_product_link"; rejected["no_resolved_asin_or_ambiguous"]+=1
                    elif len(resolved_asins)!=1: reason="multiple_product_asins_split_failed_no_price"; rejected["no_resolved_asin_or_ambiguous"]+=1
                    elif not name_candidate: reason="missing_product_name"; rejected["missing_name_or_egp_price"]+=1
                    elif not price_candidate: reason="missing_explicit_egp_price"; rejected["missing_name_or_egp_price"]+=1
                    else: reason="preview_builder_rejected_candidate"; rejected["missing_name_or_egp_price"]+=1
                    rejection_details.append({"message_id":message.id,"reason":reason,"url_hosts":sorted({(urlparse(u).hostname or "unknown").lower() for u in urls}),"url_count":len(urls),"resolved_asins":resolved_asins,"resolution_debug":list(resolution_diagnostics.values()),"name_candidate":name_candidate,"egp_price_candidate":price_candidate,"ocr_used":bool(ocr_text),"ocr_excerpt":ocr_text[:350] if ocr_text else "","message_excerpt":body[:350],})
                    continue
                # success: one candidate per ASIN
                for candidate in candidates_for_message:
                    key=str(candidate.get("source_product_key", candidate.get("source_message_id")))
                    asin=str(candidate.get("asin") or "").strip().upper()
                    if not asin or asin in already_published_asins or asin in pending_seen_asins:
                        duplicate_skipped+=1; continue
                    if key in pending_keys:
                        duplicate_skipped+=1; continue
                    candidate["source_post_url"]=f"https://t.me/{SOURCE_CHANNEL.lstrip('@')}/{message.id}"
                    candidate["source_date"]=message.date.isoformat() if message.date else None
                    candidate["ocr_used"]=bool(ocr_text)
                    candidates.append(candidate); pending_keys.add(key); pending_seen_asins.add(asin)
                # ===== END FIXED PART =====
        # FIX: Don't lose rejected posts forever. If a post was rejected (coffee machine,
        # market offers), keep last_seen below it so next run retries it.
        # Previously last_seen jumped past rejected posts and they were never retried.
        if rejection_details:
            _min_rejected = min(int(d.get("message_id", 0) or 0) for d in rejection_details if int(d.get("message_id", 0) or 0) > 0)
            if _min_rejected > 0:
                highest_seen_message_id = min(highest_seen_message_id, _min_rejected - 1)
                # Never go backwards below the previous last_seen if all rejections are old
                highest_seen_message_id = max(highest_seen_message_id, last_seen_message_id)
                # If the only rejected is the newest, we still retry it: keep last_seen at previous
                if highest_seen_message_id == last_seen_message_id and _min_rejected > last_seen_message_id:
                    # Keep last_seen as-is, so rejected newest will be rescanned
                    pass
        pending_by_key={str(i.get("source_product_key", i.get("source_message_id"))): i for i in pending_candidates if isinstance(i,dict)}
        for item in candidates: pending_by_key[str(item.get("source_product_key", item.get("source_message_id")))]=item
        pending_candidates=list(pending_by_key.values())
        output=Path("artifacts/source-offer-previews.json"); output.parent.mkdir(parents=True, exist_ok=True)
        updated_state = merge_preview_state(
            prior_state,
            last_seen_message_id=highest_seen_message_id,
            pending_candidates=pending_candidates,
            ocr_cache=ocr_cache,
        )
        state_path.write_text(
            json.dumps(updated_state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        report={"source_channel":SOURCE_CHANNEL,"posts_scanned":len(seen_messages),"photos_ocr_attempted":photo_count,"candidate_count":len(candidates),"duplicate_candidates_skipped":duplicate_skipped,"rejected_counts":rejected,"rejections":rejection_details,"candidates":pending_candidates,"pending_candidate_count":len(pending_candidates),"publishing_performed":False,"destination_channels_touched":[],"image_reuse_policy":"source images are OCR evidence only and are not cleared for republication",}
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"PREVIEW BUILD PASSED: {len(seen_messages)} source posts scanned.")
        print(f"New review-ready product candidates: {len(candidates)}")
        print(f"Pending offers retained for delivery: {len(pending_candidates)}")
        print(f"Photos OCR attempted: {photo_count}")
        print(f"OCR cache entries loaded: {ocr_cache_entries_loaded}")
        print(f"Cached OCR results reused: {ocr_cache_hits}")
        print(f"Media download time: {media_download_seconds:.2f}s")
        print(f"Image OCR processing time: {ocr_seconds:.2f}s")
        print(f"Amazon link resolution time: {link_resolution_seconds:.2f}s")
        print("No Telegram messages were sent, edited, or deleted.")
        print("No Facebook, WhatsApp, or destination channel was contacted.")
        print("Source photos were used only for OCR and are not included for republication.")
        return True
    except Exception:
        print("PREVIEW FAILED: source read or preview generation failed; details suppressed."); return False
    finally:
        if client.is_connected(): await client.disconnect()

if __name__=="__main__":
    logging.disable(logging.CRITICAL)
    try: ok=asyncio.run(run())
    except Exception: print("PREVIEW FAILED: safe startup failure; details suppressed."); ok=False
    sys.exit(0 if ok else 1)
