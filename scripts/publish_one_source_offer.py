#!/usr/bin/env python3
"""Publish one explicitly approved source offer to Telegram and Facebook."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from telethon import TelegramClient
from telethon.sessions import StringSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.source_offer import build_source_candidate
from src.source_publish import mark_platform_published, select_unpublished_candidate
from src.source_publisher import publish_facebook, publish_telegram
from src.telegram_product_card import create_telegram_product_card, find_amazon_product_details
import tempfile

REPORT_PATH = Path("artifacts/source-offer-previews.json")
STATE_PATH = Path("artifacts/source-offer-state.json")
SETTINGS_PATH = Path("config/settings.json")
SOURCE_CHANNEL = os.environ.get("SOURCE_TELEGRAM_CHANNEL", "@OffersEgyptofficial")
TARGET_CHANNEL = os.environ.get("TARGET_TELEGRAM_CHANNEL", "@cairo_deals")
TRACKING_ID = "cairodeals-21"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(STATE_PATH)


async def publish_one() -> bool:
    if os.environ.get("SOURCE_PUBLISH_ENABLED", "").lower() != "true":
        print("PUBLISH BLOCKED: explicit manual approval input is required.")
        return False
    try:
        report = load_json(REPORT_PATH)
        state = load_json(STATE_PATH) if STATE_PATH.is_file() else {}
        settings = load_json(SETTINGS_PATH)
    except (OSError, ValueError):
        print("PUBLISH BLOCKED: preview, state, or channel settings are unavailable.")
        return False

    raw_source_id = os.environ.get("SOURCE_MESSAGE_ID", "").strip()
    if not raw_source_id.isdigit():
        print("PUBLISH BLOCKED: enter the exact source post ID you reviewed.")
        return False
    selected_id = int(raw_source_id)
    meta_token = os.environ.get("META_PAGE_ACCESS_TOKEN", "")
    raw_id = os.environ.get("TELEGRAM_API_ID", "")
    api_hash = os.environ.get("TELEGRAM_API_HASH", "")
    session = os.environ.get("TELEGRAM_SESSION", "")
    if not meta_token:
        print("PUBLISH BLOCKED: Meta Page access token is missing.")
        return False
    if not raw_id.isdigit() or not api_hash or not session:
        print("PUBLISH BLOCKED: Telegram user-session credentials are missing.")
        return False

    client = TelegramClient(StringSession(session), int(raw_id), api_hash)
    try:
        await asyncio.wait_for(client.connect(), timeout=25)
        if not await client.is_user_authorized():
            print("TELEGRAM BLOCKED: user session is not authorized.")
            return False

        # Use the preview if present; otherwise fetch the exact requested source post.
        selected_report = {
            **report,
            "candidates": [
                item for item in report.get("candidates", [])
                if str(item.get("source_message_id", "")) == str(selected_id)
            ],
        }
        candidate = select_unpublished_candidate(selected_report, state)
        if candidate is None:
            source = await asyncio.wait_for(client.get_entity(SOURCE_CHANNEL), timeout=20)
            message = await asyncio.wait_for(
                client.get_messages(source, ids=selected_id), timeout=20
            )
            if message is None or int(message.id) != selected_id:
                print("PUBLISH BLOCKED: exact source message was not found.")
                return False
            body = message.message or ""
            entity_urls = [
                entity.url for entity in (message.entities or [])
                if getattr(entity, "url", None)
            ]
            candidate = build_source_candidate(
                message_id=message.id,
                message_text=body,
                entity_urls=entity_urls,
                tracking_id=TRACKING_ID,
                source_channel=SOURCE_CHANNEL,
            ) if body.strip() else None
            if candidate is None:
                print("PUBLISH BLOCKED: source post needs a valid Amazon link, product name, and EGP price.")
                return False
            candidate["source_post_url"] = f"https://t.me/{SOURCE_CHANNEL.lstrip('@')}/{message.id}"
            candidate = select_unpublished_candidate({"candidates": [candidate]}, state)
            if candidate is None:
                print("PUBLISH BLOCKED: this exact source message was already fully published.")
                return False

        message_key = str(candidate["source_message_id"])
        platform_status = dict(state.get("platform_status", {}).get(message_key, {}))
        caption = str(candidate.get("caption_preview") or "").strip()
        live = find_amazon_product_details(str(candidate.get("asin") or "")) or {}
        if not live.get("title") or not live.get("image_url"):
            print("PUBLISH BLOCKED: matching Amazon product image/title could not be verified.")
            return False
        image_url = str(live["image_url"])
        product_name = str(candidate.get("product_name_source") or live["title"])
        product_price = str(live.get("price") or candidate.get("advertised_price") or "")
        if not caption:
            print("PUBLISH BLOCKED: candidate caption is empty.")
            return False

        # Confirm each destination independently. A retry skips only a destination
        # that already confirmed this exact source message.
        if not platform_status.get("facebook"):
            import time
            last_facebook = state.get("last_facebook_publish_at") or 0
            try:
                last_facebook = float(last_facebook)
            except (TypeError, ValueError):
                last_facebook = 0
            if last_facebook and time.time() - last_facebook < 2 * 60:
                print("PUBLISH BLOCKED: Facebook's two-hour publishing interval has not elapsed.")
                return False
            try:
                facebook_id = await asyncio.to_thread(
                    publish_facebook, meta_token, caption, image_url
                )
            except Exception:
                print("FACEBOOK FAILED: Telegram was not attempted; retry is safe.")
                return False
            state = mark_platform_published(state, candidate, "facebook", facebook_id)
            state["last_facebook_publish_at"] = time.time()
            save_state(state)
            print(f"FACEBOOK CONFIRMED: Meta post {facebook_id}")

        platform_status = dict(state.get("platform_status", {}).get(message_key, {}))
        target = await asyncio.wait_for(client.get_entity(TARGET_CHANNEL), timeout=20)
        saved_telegram_id = platform_status.get("telegram")
        if saved_telegram_id:
            try:
                existing = await asyncio.wait_for(
                    client.get_messages(target, ids=int(saved_telegram_id)), timeout=20
                )
            except (TypeError, ValueError):
                existing = None
            if existing is None:
                platform_status.pop("telegram", None)
                state.setdefault("platform_status", {})[message_key] = platform_status
                save_state(state)
                saved_telegram_id = None
                print("TELEGRAM STALE STATUS CLEARED: saved destination message does not exist.")
        if not saved_telegram_id:
            with tempfile.TemporaryDirectory(prefix="cairo-manual-card-") as temp_dir:
                card_path = create_telegram_product_card(
                    asin=str(candidate["asin"]),
                    product_name=product_name,
                    price=product_price,
                    output_path=Path(temp_dir) / "telegram-product-card.jpg",
                    image_url=image_url,
                )
                telegram_id = await asyncio.wait_for(
                    publish_telegram(client, target, caption, str(card_path)), timeout=60
                )
            state = mark_platform_published(state, candidate, "telegram", telegram_id)
            save_state(state)
            print(f"TELEGRAM CONFIRMED: destination message {telegram_id}")

        complete = state.get("platform_status", {}).get(message_key, {})
        if complete.get("facebook") and complete.get("telegram"):
            print("PUBLISH CONFIRMED: one offer delivered to Facebook and Telegram.")
            return True
        print("PUBLISH PARTIAL: confirmed platform IDs were saved for a safe retry.")
        return False
    except Exception:
        print("PUBLISH FAILED: delivery was not fully confirmed; saved platform state is retained.")
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
