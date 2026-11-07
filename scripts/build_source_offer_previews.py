#!/usr/bin/env python3
"""Read source Telegram posts and build non-publishing, review-only offer previews."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps
import pytesseract
from telethon import TelegramClient
from telethon.sessions import StringSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.source_offer import build_source_candidate

SOURCE_CHANNEL = "@amzon44"
POST_LIMIT = 30
PHOTO_LIMIT = 10
TRACKING_ID = "cairodeals-21"


def image_ocr(path: str) -> str:
    with Image.open(path) as source:
        image = source.convert("RGB")
        if max(image.size) < 1600:
            factor = min(2.0, 1600 / max(image.size))
            image = image.resize(
                (int(image.width * factor), int(image.height * factor)),
                Image.Resampling.LANCZOS,
            )
        gray = ImageOps.autocontrast(ImageOps.grayscale(image))
        enhanced = ImageEnhance.Contrast(gray).enhance(1.5)
        outputs = []
        for candidate in (image, enhanced):
            for psm in (6, 11):
                outputs.append(pytesseract.image_to_string(
                    candidate, lang="ara+eng", config=f"--oem 1 --psm {psm}"
                ))
        return "\n".join(outputs)


async def run() -> bool:
    raw_id = os.environ.get("TELEGRAM_API_ID", "")
    api_hash = os.environ.get("TELEGRAM_API_HASH", "")
    session = os.environ.get("TELEGRAM_SESSION", "")
    if not raw_id.isdigit() or not api_hash or not session:
        print("PREVIEW FAILED: Telegram secrets are missing.")
        return False

    client = TelegramClient(StringSession(session), int(raw_id), api_hash)
    candidates = []
    seen_messages = set()
    seen_asins = set()
    state_path = Path("artifacts/source-offer-state.json")
    try:
        prior_state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    except (OSError, ValueError):
        prior_state = {}
    prior_message_ids = {int(value) for value in prior_state.get("message_ids", [])}
    prior_asins = {str(value).upper() for value in prior_state.get("asins", [])}
    duplicate_skipped = 0
    rejected = {"no_resolved_asin_or_ambiguous": 0, "missing_name_or_egp_price": 0, "photo_ocr_failed": 0}
    photo_count = 0
    try:
        await asyncio.wait_for(client.connect(), timeout=25)
        if not await client.is_user_authorized():
            print("PREVIEW FAILED: Telegram session is not authorized.")
            return False
        source = await asyncio.wait_for(client.get_entity(SOURCE_CHANNEL), timeout=20)
        with tempfile.TemporaryDirectory(prefix="cairo-source-preview-") as temp_dir:
            async for message in client.iter_messages(source, limit=POST_LIMIT):
                if message.id in seen_messages:
                    continue
                seen_messages.add(message.id)
                body = message.message or ""
                entity_urls = [
                    entity.url for entity in (message.entities or [])
                    if getattr(entity, "url", None)
                ]
                ocr_text = ""
                if message.photo and photo_count < PHOTO_LIMIT:
                    photo_count += 1
                    try:
                        path = str(Path(temp_dir) / f"source_{message.id}.jpg")
                        downloaded = await asyncio.wait_for(
                            client.download_media(message, file=path), timeout=30
                        )
                        if downloaded and Path(downloaded).is_file():
                            ocr_text = image_ocr(downloaded)
                    except Exception:
                        rejected["photo_ocr_failed"] += 1

                try:
                    candidate = build_source_candidate(
                        message_id=message.id,
                        message_text=body,
                        ocr_text=ocr_text,
                        entity_urls=entity_urls,
                        tracking_id=TRACKING_ID,
                    )
                except Exception:
                    candidate = None
                if candidate is None:
                    if not any(re.search(r"https?://", value) for value in [body, *entity_urls]):
                        rejected["no_resolved_asin_or_ambiguous"] += 1
                    else:
                        rejected["missing_name_or_egp_price"] += 1
                    continue
                if (
                    candidate["asin"] in seen_asins
                    or candidate["asin"] in prior_asins
                    or message.id in prior_message_ids
                ):
                    duplicate_skipped += 1
                    continue
                seen_asins.add(candidate["asin"])
                candidate["source_post_url"] = f"https://t.me/amzon44/{message.id}"
                candidate["source_date"] = message.date.isoformat() if message.date else None
                candidate["ocr_used"] = bool(ocr_text)
                candidates.append(candidate)

        output = Path("artifacts/source-offer-previews.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({
            "message_ids": list((prior_message_ids | {item["source_message_id"] for item in candidates}))[-1000:],
            "asins": list((prior_asins | {item["asin"] for item in candidates}))[-1000:],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        report = {
            "source_channel": SOURCE_CHANNEL,
            "posts_scanned": len(seen_messages),
            "photos_ocr_attempted": photo_count,
            "candidate_count": len(candidates),
            "duplicate_candidates_skipped": duplicate_skipped,
            "rejected_counts": rejected,
            "candidates": candidates,
            "publishing_performed": False,
            "destination_channels_touched": [],
            "image_reuse_policy": "source images are OCR evidence only and are not cleared for republication",
        }
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"PREVIEW BUILD PASSED: {len(seen_messages)} source posts scanned.")
        print(f"Review-ready product candidates: {len(candidates)}")
        print(f"Photos OCR attempted: {photo_count}")
        print("No Telegram messages were sent, edited, or deleted.")
        print("No Facebook, WhatsApp, or destination channel was contacted.")
        print("Source photos were used only for OCR and are not included for republication.")
        return True
    except Exception:
        print("PREVIEW FAILED: source read or preview generation failed; details suppressed.")
        return False
    finally:
        if client.is_connected():
            await client.disconnect()


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    try:
        ok = asyncio.run(run())
    except Exception:
        print("PREVIEW FAILED: safe startup failure; details suppressed.")
        ok = False
    sys.exit(0 if ok else 1)
