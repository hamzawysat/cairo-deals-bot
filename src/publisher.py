"""Telegram text publisher using Telegram's automatic link preview."""
import json
import requests


class PublishError(RuntimeError):
    pass


def send_telegram(token: str, channel_id: str, text: str, timeout: int = 20) -> str:
    """Send compact ad text and configure Telegram's side link preview."""
    if not token or not channel_id:
        raise PublishError("Telegram credentials are missing")

    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={
            "chat_id": channel_id,
            "text": text,
            "link_preview_options": json.dumps({
                "prefer_small_media": True,
                "show_above_text": False,
            }),
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise PublishError(payload.get("description", "Telegram rejected the message"))
    return str(payload["result"]["message_id"])
