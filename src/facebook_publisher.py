"""Direct Facebook Page publishing through the Meta Graph API."""
from __future__ import annotations
import os
import requests

GRAPH_API_VERSION = "v27.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


class FacebookPublishError(RuntimeError):
    """Meta rejected a Facebook Page post or could not be reached."""


def get_page_identity(page_access_token: str, timeout: int = 20) -> dict:
    if not page_access_token:
        raise FacebookPublishError("Meta Page access token is missing")
    try:
        response = requests.get(
            f"{GRAPH_API_BASE}/me",
            params={"fields": "id,name", "access_token": page_access_token},
            timeout=timeout,
        )
        response.raise_for_status()
        result = response.json()
    except requests.RequestException as exc:
        raise FacebookPublishError("Meta Page identity request failed") from exc
    except ValueError as exc:
        raise FacebookPublishError("Meta returned invalid identity JSON") from exc
    if result.get("error"):
        raise FacebookPublishError(str(result["error"].get("message", "Meta identity validation failed")))
    page_id, page_name = str(result.get("id") or "").strip(), str(result.get("name") or "").strip()
    expected_name = os.getenv("META_PAGE_NAME", "cairodeals").strip()
    if not page_id or not page_name:
        raise FacebookPublishError("Meta token did not resolve to a Facebook Page")
    if expected_name and page_name.casefold() != expected_name.casefold():
        raise FacebookPublishError(f"Meta token resolved to '{page_name}', not expected Page '{expected_name}'")
    return {"id": page_id, "name": page_name}


def send_facebook(page_access_token: str, text: str, photo_url: str | None = None, timeout: int = 30) -> str:
    if not page_access_token:
        raise FacebookPublishError("Meta Page access token is missing")
    if not text or not text.strip():
        raise FacebookPublishError("Facebook post text is empty")
    if photo_url and not photo_url.startswith("https://"):
        raise FacebookPublishError("Facebook image URL must use HTTPS")
    page = get_page_identity(page_access_token, timeout=min(timeout, 20))
    endpoint = f"{GRAPH_API_BASE}/{page['id']}/photos" if photo_url else f"{GRAPH_API_BASE}/{page['id']}/feed"
    payload = {"access_token": page_access_token, "caption" if photo_url else "message": text}
    if photo_url:
        payload["url"] = photo_url
    try:
        response = requests.post(endpoint, data=payload, timeout=timeout)
        response.raise_for_status()
        result = response.json()
    except requests.RequestException as exc:
        raise FacebookPublishError("Meta publish request failed") from exc
    except ValueError as exc:
        raise FacebookPublishError("Meta returned invalid publish JSON") from exc
    if result.get("error"):
        raise FacebookPublishError(str(result["error"].get("message", "Meta rejected the post")))
    post_id = result.get("post_id") or result.get("id")
    if not post_id:
        raise FacebookPublishError("Meta did not confirm successful post creation")
    return str(post_id)
