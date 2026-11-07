#!/usr/bin/env python3
"""Read-only inspection of recent source posts; never downloads or publishes media."""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from telethon import TelegramClient
from telethon.sessions import StringSession

from src.processor import extract_single_asin

SOURCE_CHANNEL = "@amzon44"
SAMPLE_LIMIT = 10


async def inspect() -> bool:
    raw_id = os.environ.get("TELEGRAM_API_ID", "")
    api_hash = os.environ.get("TELEGRAM_API_HASH", "")
    session = os.environ.get("TELEGRAM_SESSION", "")
    if not raw_id.isdigit() or not api_hash or not session:
        print("INSPECTION FAILED: required Telegram secrets are missing.")
        return False

    client = TelegramClient(StringSession(session), int(raw_id), api_hash)
    try:
        await asyncio.wait_for(client.connect(), timeout=25)
        if not await client.is_user_authorized():
            print("INSPECTION FAILED: Telegram session is not authorized.")
            return False
        source = await asyncio.wait_for(client.get_entity(SOURCE_CHANNEL), timeout=20)

        total = photos = videos = documents = text_only = with_asin = without_asin = 0
        async for message in client.iter_messages(source, limit=SAMPLE_LIMIT):
            total += 1
            if message.photo:
                photos += 1
            elif message.video:
                videos += 1
            elif message.document:
                documents += 1
            else:
                text_only += 1

            body = message.message or ""
            if extract_single_asin(body):
                with_asin += 1
            else:
                without_asin += 1

        print("READ-ONLY SOURCE INSPECTION PASSED.")
        print(f"Recent posts inspected: {total}")
        print(f"Photo posts: {photos}; video posts: {videos}; other documents: {documents}; text/other: {text_only}")
        print(f"Posts with one directly extractable Amazon ASIN: {with_asin}")
        print(f"Posts without one unambiguous directly extractable ASIN: {without_asin}")
        print("Media was not downloaded. No messages were sent, edited, or deleted.")
        return total > 0
    except Exception:
        print("INSPECTION FAILED: source read or inspection failed; details suppressed for secret safety.")
        return False
    finally:
        if client.is_connected():
            await client.disconnect()


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    try:
        ok = asyncio.run(inspect())
    except Exception:
        print("INSPECTION FAILED: safe startup failure; details suppressed.")
        ok = False
    sys.exit(0 if ok else 1)
