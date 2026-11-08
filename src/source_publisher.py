"""Destination adapters for source-monitor; no automatic run loop lives here."""
from __future__ import annotations

from src.facebook_publisher import send_facebook


def publish_facebook(
    buffer_api_key: str, facebook_channel_id: str,
    caption: str, photo_url: str | None = None,
) -> str:
    """Publish through the existing Buffer integration."""
    return send_facebook(buffer_api_key, facebook_channel_id, caption, photo_url)


async def publish_telegram(
    telegram_client, target_entity, caption: str, photo_path: str | None = None,
) -> str:
    """Publish with the authenticated Telegram user session."""
    if photo_path:
        message = await telegram_client.send_file(
            target_entity, photo_path, caption=caption, force_document=False, parse_mode="md"
        )
    else:
        message = await telegram_client.send_message(
            target_entity, caption, link_preview=True, parse_mode="md"
        )
    return str(message.id)
