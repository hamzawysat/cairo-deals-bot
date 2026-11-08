#!/usr/bin/env python3
"""Publish queued Amazon source offers to the enabled Cairo Deals destinations."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

from telethon import TelegramClient
from telethon.sessions import StringSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.source_publish import mark_platform_published
from src.source_publisher import publish_facebook, publish_telegram
from src.telegram_product_card import create_telegram_product_card, find_amazon_product_details

STATE_PATH = Path("artifacts/source-offer-state.json")
SETTINGS_PATH = Path("config/settings.json")

TELEGRAM_LINK = "https://t.me/cairo_deals"
FACEBOOK_LINK = "https://www.facebook.com/share/19hQqVpCuG/"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(STATE_PATH)


def _rebuild_caption(candidate: dict, *, for_telegram: bool = False) -> str:
    """Rebuild caption at publish time so old stored captions don't keep the removed disclaimer.

    Old pending candidates were stored with the removed disclaimer and without
    the follow links. Rebuilding here makes them publish with the current format.
    For Telegram, links are embedded in the words (Markdown) so the long URLs
    don't eat the whole ad. For Facebook/Buffer, plain URLs are kept because
    Buffer treats the caption as plain text.
    """
    name = str(candidate.get("product_name_source") or "").strip()
    price = str(candidate.get("advertised_price") or "").strip()
    url = str(candidate.get("affiliate_url") or "").strip()
    if not name or not url:
        return str(candidate.get("caption_preview") or "").strip()
    if for_telegram:
        follow = f"[تابعنا على تليجرام]({TELEGRAM_LINK}) | [تابعنا على فيسبوك]({FACEBOOK_LINK})"
    else:
        follow = f"تابعنا: تليجرام {TELEGRAM_LINK} | فيسبوك {FACEBOOK_LINK}"
    lines = [
        "✨ عرض جديد من Cairo Deals",
        "",
        f"📦 {name}",
        "",
        f"💰 السعر المعلن: {price}" if price else "",
        "",
        "🛒 تفاصيل المنتج والشراء من هنا:",
        url,
        "",
        follow,
    ]
    return "\n".join([ln for ln in lines if ln != ""])



FACEBOOK_INTERVAL_SECONDS = 2 * 60 * 60  # Facebook every 2 hours, Telegram stays every 2 minutes

def _facebook_due(state: dict) -> bool:
    """True if Facebook hasn't published in the last 2 hours (or never)."""
    import time
    last = state.get("last_facebook_publish_at") or 0
    try:
        last = float(last)
    except (TypeError, ValueError):
        return True
    return (time.time() - last) >= FACEBOOK_INTERVAL_SECONDS

def _telegram_post_url(telegram_id: str) -> str | None:
    """Public link to the Telegram post - Buffer uses it to fetch the card image."""
    tid = str(telegram_id or "").strip()
    if not tid.isdigit():
        return None
    return f"https://t.me/cairo_deals/{tid}"


FACEBOOK_INTERVAL_SECONDS = 2 * 60 * 60

def _facebook_due(state: dict) -> bool:
    import time
    last = state.get("last_facebook_publish_at") or 0
    try:
        last = float(last)
    except (TypeError, ValueError):
        return True
    return (time.time() - last) >= FACEBOOK_INTERVAL_SECONDS

def _telegram_post_url(telegram_id: str) -> str | None:
    tid = str(telegram_id or "").strip()
    if not tid.isdigit():
        return None
    return f"https://t.me/cairo_deals/{tid}"

async def publish_pending() -> bool:
    if os.environ.get("SOURCE_AUTO_PUBLISH_ENABLED", "").strip().lower() != "true":
        print("AUTO-PUBLISH BLOCKED: repository variable SOURCE_AUTO_PUBLISH_ENABLED is not true.")
        return False

    try:
        settings = load_json(SETTINGS_PATH)
        state = load_json(STATE_PATH) if STATE_PATH.is_file() else {}
    except (OSError, ValueError):
        print("AUTO-PUBLISH BLOCKED: settings or delivery state could not be loaded.")
        return False

    if settings.get("dry_run", True) is not False:
        print("AUTO-PUBLISH BLOCKED: config/settings.json still has dry_run enabled.")
        return False
    channels = settings.get("channels", {})
    if not channels.get("telegram", {}).get("enabled", False):
        print("AUTO-PUBLISH BLOCKED: Telegram destination is disabled in config/settings.json.")
        return False
    if not channels.get("facebook", {}).get("enabled", False):
        print("AUTO-PUBLISH BLOCKED: Facebook destination is disabled in config/settings.json.")
        return False
    if settings.get("safety", {}).get("require_image", False):
        print("AUTO-PUBLISH BLOCKED: image reuse is required but no approved product-image source is configured.")
        return False

    pending = list(state.get("pending_candidates", []))
    if not pending:
        print("AUTO-PUBLISH: no eligible pending Amazon offers.")
        return True

    max_posts = settings.get("max_posts_per_run", 1)
    try:
        max_posts = max(1, min(int(max_posts), 10))
    except (TypeError, ValueError):
        max_posts = 1

    raw_id = os.environ.get("TELEGRAM_API_ID", "")
    api_hash = os.environ.get("TELEGRAM_API_HASH", "")
    session = os.environ.get("TELEGRAM_SESSION", "")
    buffer_key = os.environ.get("BUFFER_API_KEY", "")
    facebook_channel_id = str(channels.get("facebook", {}).get("channel_id") or "").strip()
    if not raw_id.isdigit() or not api_hash or not session:
        print("AUTO-PUBLISH BLOCKED: Telegram credentials are missing.")
        return False
    if not buffer_key or not facebook_channel_id:
        print("AUTO-PUBLISH BLOCKED: Buffer credentials or Facebook channel ID are missing.")
        return False

    client = TelegramClient(StringSession(session), int(raw_id), api_hash)
    all_ok = True
    try:
        await asyncio.wait_for(client.connect(), timeout=25)
        if not await client.is_user_authorized():
            print("AUTO-PUBLISH BLOCKED: Telegram session is not authorized.")
            return False
        target = await asyncio.wait_for(
            client.get_entity(os.environ.get("TARGET_TELEGRAM_CHANNEL", "@cairo_deals")),
            timeout=20,
        )

        processed = 0
        attempted = 0
        for candidate in pending:
            if attempted >= max_posts:
                break
            attempted += 1
            try:
                message_id = int(candidate["source_message_id"])
                # FIX: refresh price/name from Amazon page itself (no API) before building caption.
                # Source message price can be stale (146 vs live 159.99). Live page wins.
                try:
                    _live = find_amazon_product_details(str(candidate.get("asin") or ""))
                    if _live.get("price"):
                        candidate = dict(candidate); candidate["advertised_price"] = _live["price"]
                    if _live.get("title"):
                        # Amazon og:title is clean: "بخاخ سبلاش للجسم جولد سبيل..." - use it if source name is garbled
                        candidate = dict(candidate); candidate["product_name_source"] = _live["title"]
                except Exception:
                    pass
                # FIX: rebuild caption at publish time instead of using old stored caption_preview
                caption = _rebuild_caption(candidate, for_telegram=False)
                telegram_caption = _rebuild_caption(candidate, for_telegram=True)
                if not caption or not candidate.get("affiliate_url") or not candidate.get("asin"):
                    print(f"SKIPPED source message {message_id}: candidate data is incomplete.")
                    continue
            except (KeyError, TypeError, ValueError):
                print("SKIPPED malformed pending candidate.")
                continue

            key = str(message_id)
            # NEW ORDER: Telegram first, then Facebook takes image link from Telegram.
            # Telegram every run. Facebook only if 2 hours passed since last Facebook post.
            platform_status = dict(state.get("platform_status", {}).get(key, {}))
            telegram_id = platform_status.get("telegram")
            if not telegram_id:
                try:
                    with tempfile.TemporaryDirectory(prefix="cairo-telegram-card-") as temp_dir:
                        card_path = create_telegram_product_card(
                            asin=str(candidate["asin"]),
                            product_name=str(candidate["product_name_source"]),
                            price=str(candidate["advertised_price"]),
                            output_path=Path(temp_dir) / "telegram-product-card.jpg",
                        )
                        telegram_id = await asyncio.wait_for(
                            publish_telegram(client, target, telegram_caption, str(card_path)), timeout=60
                        )
                    state = mark_platform_published(state, candidate, "telegram", telegram_id)
                    save_state(state)
                    print(f"TELEGRAM CONFIRMED for source {message_id}: {telegram_id}")
                except Exception as exc:
                    all_ok = False
                    print(f"TELEGRAM FAILED for source {message_id}: {type(exc).__name__}")
                    continue
            platform_status = dict(state.get("platform_status", {}).get(key, {}))
            if not platform_status.get("facebook"):
                if not _facebook_due(state):
                    print(f"FACEBOOK SKIPPED for source {message_id}: less than 2 hours since last Facebook post.")
                else:
                    try:
                        # FIX: Buffer needs a direct *.jpg URL, not a Telegram post page (HTML).
                        # Telegram post link caused BufferPublishError, so send text-only for now.
                        facebook_id = await asyncio.to_thread(
                            publish_facebook, buffer_key, facebook_channel_id, caption, None
                        )
                        state = mark_platform_published(state, candidate, "facebook", facebook_id)
                        import time as _time
                        state["last_facebook_publish_at"] = _time.time()
                        save_state(state)
                        print(f"FACEBOOK CONFIRMED for source {message_id}: {facebook_id}")
                    except Exception as exc:
                        all_ok = False
                        print(f"FACEBOOK FAILED for source {message_id}: {type(exc).__name__}")
                        continue
            final_status = state.get("platform_status", {}).get(key, {})
            if final_status.get("telegram") and final_status.get("facebook"):
                published = {int(value) for value in state.get("published_message_ids", [])}
                published.add(message_id)
                state["published_message_ids"] = sorted(published)[-1000:]
                state["pending_candidates"] = [
                    item for item in state.get("pending_candidates", [])
                    if str(item.get("source_message_id")) != key
                ]
                save_state(state)
                processed += 1
                print(f"OFFER COMPLETE: source message {message_id} delivered to both destinations.")

        print(f"AUTO-PUBLISH FINISHED: {processed} offer(s) completed this run.")
        return all_ok
    except Exception as exc:
        print(f"AUTO-PUBLISH FAILED: {type(exc).__name__}; pending offers were retained.")
        return False
    finally:
        if client.is_connected():
            await client.disconnect()


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    try:
        success = asyncio.run(publish_pending())
    except Exception:
        print("AUTO-PUBLISH FAILED: safe startup failure.")
        success = False
    sys.exit(0 if success else 1)
