"""Telegram publishing with full-frame product photos and API-level validation."""
from io import BytesIO

import requests
from PIL import Image, ImageOps


class PublishError(RuntimeError):
    pass


class PhotoPreparationError(PublishError):
    """A product photo could not be downloaded or prepared; try another offer."""

    pass


def _prepare_full_frame_photo(photo_url: str, timeout: int) -> BytesIO:
    """Fit the complete source image inside a square canvas without cropping."""
    try:
        response = requests.get(photo_url, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise PhotoPreparationError(f"Could not download product image: {exc}") from exc
    if len(response.content) > 10 * 1024 * 1024:
        raise PhotoPreparationError("Product image exceeds the 10 MB download limit")

    try:
        with Image.open(BytesIO(response.content)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((1000, 1000), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (1200, 1200), "white")
            x = (1200 - image.width) // 2
            y = (1200 - image.height) // 2
            canvas.paste(image, (x, y))
            output = BytesIO()
            canvas.save(output, format="JPEG", quality=90, optimize=True)
            output.seek(0)
            return output
    except (OSError, ValueError) as exc:
        raise PhotoPreparationError(f"Could not prepare product image: {exc}") from exc


def send_telegram(
    token: str,
    channel_id: str,
    text: str,
    timeout: int = 20,
    photo_url: str | None = None,
) -> str:
    if not token or not channel_id:
        raise PublishError("Telegram credentials are missing")

    files = None
    if photo_url:
        endpoint = "sendPhoto"
        data = {"chat_id": channel_id, "caption": text}
        photo = _prepare_full_frame_photo(photo_url, timeout)
        files = {"photo": ("product.jpg", photo, "image/jpeg")}
    else:
        endpoint = "sendMessage"
        data = {"chat_id": channel_id, "text": text, "disable_web_page_preview": False}

    response = requests.post(
        f"https://api.telegram.org/bot{token}/{endpoint}",
        data=data,
        files=files,
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise PublishError(payload.get("description", "Telegram rejected the message"))
    return str(payload["result"]["message_id"])
