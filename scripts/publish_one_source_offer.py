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
from src.source_publish import mark_platform_published, select_unpublished_candidate
from src.source_publisher import publish_facebook, publish_telegram

REPORT_PATH = Path("artifacts/source-offer-previews.json")
STATE_PATH = Path("artifacts/source-offer-state.json")
SETTINGS_PATH = Path("config/settings.json")
TARGET_CHANNEL = os.environ.get("TARGET_TELEGRAM_CHANNEL", "@cairo_deals")


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
    selected_report = {
        **report,
        "candidates": [
            item for item in report.get("candidates", [])
            if int(item.get("source_message_id", -1)) == selected_id
        ],
    }
    candidate = select_unpublished_candidate(selected_report, state)
    if not candidate:
        print("PUBLISH BLOCKED: selected source post is absent, invalid, or already published.")
        return False

    buffer_key = os.environ.get("BUFFER_API_KEY", "")
    facebook_cfg = settings.get("channels", {}).get("facebook", {})
    facebook_channel_id = str(facebook_cfg.get("channel_id") or "").strip()
    raw_id = os.environ.get("TELEGRAM_API_ID", "")
    api_hash = os.environ.get("TELEGRAM_API_HASH", "")
    session = os.environ.get("TELEGRAM_SESSION", "")
    if not buffer_key or not facebook_channel_id:
        print("PUBLISH BLOCKED: Buffer API key or Facebook channel ID is missing.")
        return False
    if not raw_id.isdigit() or not api_hash or not session:
        print("PUBLISH BLOCKED: Telegram user-session credentials are missing.")
        return False

    message_key = str(candidate["source_message_id"])
    platform_status = dict(state.get("platform_status", {}).get(message_key, {}))
    caption = str(candidate.get("caption_preview") or "").strip()
    if not caption:
        print("PUBLISH BLOCKED: candidate caption is empty.")
        return False

    client = TelegramClient(StringSession(session), int(raw_id), api_hash)
    try:
        # Publish Facebook first. Its confirmed ID is saved immediately so a Telegram
        # failure can be retried without creating a duplicate Facebook post.
        if not platform_status.get("facebook"):
            try:
                facebook_id = await asyncio.to_thread(
                    publish_facebook, buffer_key, facebook_channel_id, caption, None
                )
            except Exception:
                print("FACEBOOK FAILED: Telegram was not attempted; retry is safe.")
                return False
            state = mark_platform_published(state, candidate, "facebook", facebook_id)
            save_state(state)
            print(f"FACEBOOK CONFIRMED: Buffer post {facebook_id}")

        platform_status = dict(state.get("platform_status", {}).get(message_key, {}))
        if not platform_status.get("telegram"):
            await asyncio.wait_for(client.connect(), timeout=25)
            if not await client.is_user_authorized():
                print("TELEGRAM BLOCKED: user session is not authorized.")
                return False
            target = await asyncio.wait_for(client.get_entity(TARGET_CHANNEL), timeout=20)
            telegram_id = await asyncio.wait_for(
                publish_telegram(client, target, caption, None), timeout=45
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
