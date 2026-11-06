"""Facebook Page photo publishing through Meta Graph API."""
from io import BytesIO

import requests

from .publisher import PublishError, _prepare_full_frame_photo


def publish_facebook_photo(
    page_id: str,
    page_access_token: str,
    caption: str,
    photo_url: str,
    graph_api_version: str = "v26.0",
    timeout: int = 20,
) -> str:
    """Publish one full-frame product photo to a Facebook Page and return its post ID.

    This function is intentionally not wired into the scheduled Telegram workflow.
    Callers must explicitly invoke it after Facebook credentials are configured.
    """
    page_id = (page_id or "").strip()
    page_access_token = (page_access_token or "").strip()
    graph_api_version = (graph_api_version or "").strip()
    if not page_id or not page_access_token:
        raise PublishError("Facebook Page ID and Page Access Token are required")
    if not graph_api_version or "/" in graph_api_version:
        raise PublishError("A valid Meta Graph API version is required")
    if not photo_url or not photo_url.startswith("https://"):
        raise PublishError("Facebook product image URL must use HTTPS")

    photo = _prepare_full_frame_photo(photo_url, timeout)
    endpoint = (
        f"https://graph.facebook.com/{graph_api_version}/{page_id}/photos"
    )
    files = {
        "source": ("product.jpg", photo, "image/jpeg"),
    }
    data = {
        "caption": caption,
        "published": "true",
        "access_token": page_access_token,
    }

    try:
        response = requests.post(
            endpoint,
            data=data,
            files=files,
            timeout=timeout,
        )
        payload = response.json()
    except requests.RequestException as exc:
        raise PublishError(f"Facebook request failed: {exc}") from exc
    except ValueError as exc:
        raise PublishError("Facebook returned an invalid JSON response") from exc

    if not response.ok or payload.get("error"):
        error = payload.get("error", {})
        message = error.get("message") or response.text or "Facebook rejected the post"
        code = error.get("code")
        suffix = f" (code {code})" if code is not None else ""
        raise PublishError(f"Facebook publishing failed: {message}{suffix}")

    post_id = payload.get("post_id") or payload.get("id")
    if not post_id:
        raise PublishError("Facebook response did not include a post ID")
    return str(post_id)
