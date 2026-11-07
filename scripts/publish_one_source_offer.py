#!/usr/bin/env python3
"""Publish exactly one reviewed source offer to Telegram when explicitly enabled."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

import requests
from PIL import Image, ImageOps
from telethon import TelegramClient
from telethon.sessions import StringSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.source_publish import (
    mark_candidate_published,
    select_unpublished_candidate,
    validate_approved_image_record,
)

REPORT_PATH = Path("artifacts/source-offer-previews.json")
STATE_PATH = Path("artifacts/source-offer-state.json")
IMAGE_MANIFEST_PATH = Path("config/approved_product_images.json")
TARGET_CHANNEL = os.environ.get("TARGET_TELEGRAM_CHANNEL", "@cairo_deals")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def prepare_approved_image(url: str, destination: Path) -> None:
    response = requests.get(url, timeout=(5, 15), stream=True, headers={
        "User-Agent": "CairoDealsPublisher/1.0",
    })
    try:
        response.raise_for_status()
        content = response.raw.read(10 * 1024 * 1024 + 1)
        if len(content) > 10 * 1024 * 1024:
            raise ValueError("Approved image exceeds 10 MB.")
        from io import BytesIO
        with Image.open(BytesIO(content)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((1000, 1000), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (1200, 1200), "white")
            canvas.paste(image, ((1200 - image.width) // 2, (1200 - image.height) // 2))
            canvas.save(destination, format="JPEG", quality=90, optimize=True)
    finally:
        response.close()


async def publish_one() -> bool:
    if os.environ.get("SOURCE_PUBLISH_ENABLED", "").lower() != "true":
        print("PUBLISH BLOCKED: explicit publish approval input is required.")
        return False
    try:
        report = load_json(REPORT_PATH)
        state = load_json(STATE_PATH) if STATE_PATH.is_file() else {}
        manifest = load_json(IMAGE_MANIFEST_PATH)
    except (OSError, ValueError):
        print("PUBLISH BLOCKED: preview, state, or approved-image manifest is unavailable.")
        return False

    candidate = select_unpublished_candidate(report, state)
    if not candidate:
        print("PUBLISH BLOCKED: no new review-ready source offer is available.")
        return False
    asin = str(candidate["asin"]).upper()
    image_url = validate_approved_image_record(manifest.get(asin))
    if not image_url:
        print("PUBLISH BLOCKED: this ASIN has no image with documented reuse permission.")
        return False

    raw_id = os.environ.get("TELEGRAM_API_ID", "")
    api_hash = os.environ.get("TELEGRAM_API_HASH", "")
    session = os.environ.get("TELEGRAM_SESSION", "")
    if not raw_id.isdigit() or not api_hash or not session:
        print("PUBLISH BLOCKED: Telegram credentials are missing.")
        return False

    client = TelegramClient(StringSession(session), int(raw_id), api_hash)
    try:
        with tempfile.TemporaryDirectory(prefix="cairo-approved-image-") as temp_dir:
            photo_path = Path(temp_dir) / "approved-product.jpg"
            try:
                await asyncio.to_thread(prepare_approved_image, image_url, photo_path)
            except Exception:
                print("PUBLISH BLOCKED: approved product image could not be validated.")
                return False

            await asyncio.wait_for(client.connect(), timeout=25)
            if not await client.is_user_authorized():
                print("PUBLISH BLOCKED: Telegram session is not authorized.")
                return False
            target = await asyncio.wait_for(client.get_entity(TARGET_CHANNEL), timeout=20)
            message = await asyncio.wait_for(
                client.send_file(
                    target,
                    str(photo_path),
                    caption=candidate["caption_preview"],
                    force_document=False,
                ),
                timeout=45,
            )

        updated_state = mark_candidate_published(state, candidate)
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp_state = STATE_PATH.with_suffix(".tmp")
        temp_state.write_text(
            json.dumps(updated_state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_state.replace(STATE_PATH)
        print("PUBLISH CONFIRMED: exactly one reviewed offer was sent to Telegram.")
        print(f"Source message: {candidate['source_message_id']}; destination message: {message.id}")
        return True
    except Exception:
        print("PUBLISH FAILED: Telegram delivery did not complete; details suppressed.")
        return False
    finally:
        if client.is_connected():
            await client.disconnect()


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    try:
        success = asyncio.run(publish_one())
    except Exception:
        print("PUBLISH FAILED: safe startup failure; details suppressed.")
        success = False
    sys.exit(0 if success else 1)
