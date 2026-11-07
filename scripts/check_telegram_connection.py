#!/usr/bin/env python3
"""Non-publishing smoke test for the source and destination Telegram channels."""
import asyncio
import logging
import os
import sys

from telethon import TelegramClient
from telethon.sessions import StringSession

SOURCE_CHANNEL = "@amzon44"
TARGET_CHANNEL = "@cairo_deals"


async def check() -> bool:
    raw_id = os.environ.get("TELEGRAM_API_ID", "")
    api_hash = os.environ.get("TELEGRAM_API_HASH", "")
    session = os.environ.get("TELEGRAM_SESSION", "")
    if not raw_id.isdigit() or not api_hash or not session:
        print("CHECK FAILED: required GitHub secrets are missing.")
        return False

    client = TelegramClient(StringSession(session), int(raw_id), api_hash)
    try:
        await asyncio.wait_for(client.connect(), timeout=25)
        if not await client.is_user_authorized():
            print("CHECK FAILED: Telegram session is not authorized.")
            return False
        me = await asyncio.wait_for(client.get_me(), timeout=20)
        if me is None:
            print("CHECK FAILED: Telegram account could not be verified.")
            return False
        source = await asyncio.wait_for(client.get_entity(SOURCE_CHANNEL), timeout=20)
        target = await asyncio.wait_for(client.get_entity(TARGET_CHANNEL), timeout=20)
        count = 0
        async for _ in client.iter_messages(source, limit=3):
            count += 1
        print("CHECK PASSED: account authenticated.")
        print("CHECK PASSED: source channel is accessible.")
        print("CHECK PASSED: destination channel is accessible.")
        print(f"CHECK PASSED: read access verified ({count} recent source messages checked).")
        print("No messages were sent or modified.")
        return True
    except Exception:
        # Never print exception text: provider exceptions can contain request/session details.
        print("CHECK FAILED: Telegram connection or channel access failed. Details were suppressed for secret safety.")
        return False
    finally:
        if client.is_connected():
            await client.disconnect()


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    try:
        success = asyncio.run(check())
    except Exception:
        print("CHECK FAILED: safe startup failure; details suppressed.")
        success = False
    sys.exit(0 if success else 1)
