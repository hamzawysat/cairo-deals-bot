"""Telegram publishing with API-level success validation and optional product photos."""
import requests


class PublishError(RuntimeError):
    pass


def send_telegram(
    token: str,
    channel_id: str,
    text: str,
    timeout: int = 20,
    photo_url: str | None = None,
) -> str:
    if not token or not channel_id:
        raise PublishError("Telegram credentials are missing")

    if photo_url:
        endpoint = "sendPhoto"
        data = {"chat_id": channel_id, "photo": photo_url, "caption": text}
    else:
        endpoint = "sendMessage"
        data = {"chat_id": channel_id, "text": text, "disable_web_page_preview": False}

    response = requests.post(
        f"https://api.telegram.org/bot{token}/{endpoint}",
        data=data,
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise PublishError(payload.get("description", "Telegram rejected the message"))
    return str(payload["result"]["message_id"])
