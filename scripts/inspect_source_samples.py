#!/usr/bin/env python3
"""Read-only inspection of source posts, affiliate-tag generation, and sample photos."""
from __future__ import annotations
import asyncio, logging, os, sys, tempfile
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from telethon import TelegramClient
from telethon.sessions import StringSession
from src.processor import build_amazon_affiliate_url, extract_single_asin

SOURCE_CHANNEL = "@amzon44"
SAMPLE_LIMIT = 10
PHOTO_DOWNLOAD_LIMIT = 3
TRACKING_ID = "cairodeals-21"

async def inspect() -> bool:
    raw_id, api_hash, session = (os.environ.get(k, "") for k in ("TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_SESSION"))
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
        total = photos = videos = documents = text_only = 0
        with_asin = without_asin = affiliate_tag_verified = 0
        entity_links = 0
        link_hosts = {}
        photo_attempts = photo_verified = photo_failures = 0
        with tempfile.TemporaryDirectory(prefix="source-photo-check-") as temp_dir:
            async for message in client.iter_messages(source, limit=SAMPLE_LIMIT):
                total += 1
                if message.photo:
                    photos += 1
                    if photo_attempts < PHOTO_DOWNLOAD_LIMIT:
                        photo_attempts += 1
                        try:
                            target = str(Path(temp_dir) / f"sample_{photo_attempts}.jpg")
                            downloaded = await asyncio.wait_for(client.download_media(message, file=target), timeout=35)
                            if not downloaded or not Path(downloaded).is_file():
                                raise RuntimeError("Photo download did not produce a file")
                            with Image.open(downloaded) as img:
                                img.verify()
                            with Image.open(downloaded) as img:
                                if img.width <= 0 or img.height <= 0:
                                    raise RuntimeError("Invalid image dimensions")
                            photo_verified += 1
                        except Exception:
                            photo_failures += 1
                elif message.video:
                    videos += 1
                elif message.document:
                    documents += 1
                else:
                    text_only += 1
                body = message.message or ""
                hidden_urls = []
                for entity in message.entities or []:
                    hidden_url = getattr(entity, "url", None)
                    if hidden_url:
                        hidden_urls.append(hidden_url)
                entity_links += len(hidden_urls)
                for link in hidden_urls:
                    host = (urlparse(link).hostname or "unknown").lower()
                    link_hosts[host] = link_hosts.get(host, 0) + 1
                asin = extract_single_asin(body + "\\n" + "\\n".join(hidden_urls))
                if asin:
                    with_asin += 1
                    generated = build_amazon_affiliate_url(asin, TRACKING_ID)
                    if f"tag={TRACKING_ID}" in generated:
                        affiliate_tag_verified += 1
                else:
                    without_asin += 1
        print("READ-ONLY SOURCE INSPECTION PASSED.")
        print(f"Recent posts inspected: {total}")
        print(f"Photo posts: {photos}; video posts: {videos}; other documents: {documents}; text/other: {text_only}")
        print(f"Posts with one directly extractable Amazon ASIN: {with_asin}")
        print(f"Posts without one unambiguous directly extractable ASIN: {without_asin}")
        print(f"Hidden Telegram URL entities inspected: {entity_links}")
        print("Link host counts: " + (", ".join(f"{host}={count}" for host, count in sorted(link_hosts.items())) if link_hosts else "none"))
        print(f"Egypt affiliate tag {TRACKING_ID} verified on generated links: {affiliate_tag_verified}/{with_asin}")
        print(f"Photo files downloaded and validated locally: {photo_verified}/{photo_attempts}")
        print(f"Photo validation failures: {photo_failures}")
        print("No messages were sent, edited, or deleted; temporary photo files were removed.")
        return total > 0 and affiliate_tag_verified == with_asin and photo_failures == 0
    except Exception:
        print("INSPECTION FAILED: source read or inspection failed; details suppressed for secret safety.")
        return False
    finally:
        if client.is_connected():
            await client.disconnect()

if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    try:
        success = asyncio.run(inspect())
    except Exception:
        print("INSPECTION FAILED: safe startup failure; details suppressed.")
        success = False
    sys.exit(0 if success else 1)
