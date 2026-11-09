"""Direct Facebook Page publishing through the Meta Graph API."""
from __future__ import annotations
import logging
import os
import time
from io import BytesIO

import requests
from PIL import Image, UnidentifiedImageError

GRAPH_API_VERSION = "v27.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
FACEBOOK_IMAGE_READY_DELAY_SECONDS = 3
FACEBOOK_IMAGE_READY_MAX_ATTEMPTS = 5
FACEBOOK_IMAGE_READY_RETRY_SECONDS = 2
FACEBOOK_IMAGE_MAX_BYTES = 20 * 1024 * 1024


class FacebookPublishError(RuntimeError):
    """Meta rejected a Facebook Page post or could not be reached."""


def _meta_error_details(response: requests.Response) -> str:
    """Return safe Meta diagnostics without request URLs, tokens, or full payloads."""
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return ""
    parts = []
    for key in ("message", "type", "code", "error_subcode", "fbtrace_id"):
        value = error.get(key)
        if value is not None:
            parts.append(f"{key}={str(value)[:500]}")
    return "; ".join(parts)


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
        status = getattr(getattr(exc, "response", None), "status_code", None)
        details = _meta_error_details(exc.response) if getattr(exc, "response", None) is not None else ""
        diagnostic = f" (HTTP {status}; {details})" if status or details else ""
        raise FacebookPublishError(f"Meta Page identity request failed{diagnostic}") from exc
    except ValueError as exc:
        raise FacebookPublishError("Meta returned invalid identity JSON") from exc
    if result.get("error"):
        details = _meta_error_details(response)
        raise FacebookPublishError(f"Meta identity validation failed ({details or 'unspecified Meta error'})")
    page_id, page_name = str(result.get("id") or "").strip(), str(result.get("name") or "").strip()
    expected_name = os.getenv("META_PAGE_NAME", "cairodeals").strip()
    if not page_id or not page_name:
        raise FacebookPublishError("Meta token did not resolve to a Facebook Page")
    if expected_name and page_name.casefold() != expected_name.casefold():
        raise FacebookPublishError(f"Meta token resolved to '{page_name}', not expected Page '{expected_name}'")
    return {"id": page_id, "name": page_name}


def _verify_post_visibility(post_id: str, page_access_token: str, timeout: int = 20) -> dict | None:
    """Read back publication state; verification is diagnostic and never retries a successful post."""
    try:
        response = requests.get(
            f"{GRAPH_API_BASE}/{post_id}",
            params={
                "fields": "id,is_published,is_hidden,permalink_url",
                "access_token": page_access_token,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        result = response.json()
        if isinstance(result, dict) and not result.get("error"):
            return result
        logging.warning("Facebook post visibility check returned a Meta error: %s", _meta_error_details(response))
    except (requests.RequestException, ValueError) as exc:
        logging.warning("Facebook post visibility check failed: %s", type(exc).__name__)
    return None


def _wait_for_valid_image(photo_url: str, timeout: int = 20) -> None:
    """Wait, then confirm the remote URL serves a complete, decodable image."""
    time.sleep(FACEBOOK_IMAGE_READY_DELAY_SECONDS)
    last_problem = "image was not ready"
    for attempt in range(FACEBOOK_IMAGE_READY_MAX_ATTEMPTS):
        try:
            response = requests.get(photo_url, timeout=timeout)
            response.raise_for_status()
            content_type = str(response.headers.get("Content-Type", "")).split(";", 1)[0].strip().lower()
            if not content_type.startswith("image/"):
                raise ValueError(f"unexpected content type: {content_type or 'missing'}")
            image_bytes = response.content
            if not image_bytes or len(image_bytes) > FACEBOOK_IMAGE_MAX_BYTES:
                raise ValueError("image is empty or exceeds the 20 MB limit")
            with Image.open(BytesIO(image_bytes)) as image:
                image.verify()
            with Image.open(BytesIO(image_bytes)) as image:
                if image.width < 2 or image.height < 2:
                    raise ValueError("image dimensions are too small")
            return
        except (requests.RequestException, OSError, ValueError, UnidentifiedImageError) as exc:
            last_problem = str(exc)[:200] or type(exc).__name__
            if attempt + 1 < FACEBOOK_IMAGE_READY_MAX_ATTEMPTS:
                time.sleep(FACEBOOK_IMAGE_READY_RETRY_SECONDS)
    raise FacebookPublishError(
        f"Facebook image source did not become a valid image after "
        f"{FACEBOOK_IMAGE_READY_MAX_ATTEMPTS} checks ({last_problem})"
    )


def send_facebook(page_access_token: str, text: str, photo_url: str | None = None, timeout: int = 30) -> str:
    if not page_access_token:
        raise FacebookPublishError("Meta Page access token is missing")
    if not text or not text.strip():
        raise FacebookPublishError("Facebook post text is empty")
    if photo_url and not photo_url.startswith("https://"):
        raise FacebookPublishError("Facebook image URL must use HTTPS")
    page = get_page_identity(page_access_token, timeout=min(timeout, 20))
    endpoint = f"{GRAPH_API_BASE}/{page['id']}/photos" if photo_url else f"{GRAPH_API_BASE}/{page['id']}/feed"
    payload = {"access_token": page_access_token, "published": "true", "caption" if photo_url else "message": text}
    if photo_url:
        payload["url"] = photo_url
        # The bot waits, downloads, and decodes the image before Meta receives its URL.
        _wait_for_valid_image(photo_url, timeout=min(timeout, 20))
    try:
        response = requests.post(endpoint, data=payload, timeout=timeout)
        response.raise_for_status()
        result = response.json()
    except requests.RequestException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        details = _meta_error_details(exc.response) if getattr(exc, "response", None) is not None else ""
        diagnostic = f" (HTTP {status}; {details})" if status or details else ""
        raise FacebookPublishError(f"Meta publish request failed{diagnostic}") from exc
    except ValueError as exc:
        raise FacebookPublishError("Meta returned invalid publish JSON") from exc
    if result.get("error"):
        details = _meta_error_details(response)
        raise FacebookPublishError(f"Meta rejected the post ({details or 'unspecified Meta error'})")
    post_id = result.get("post_id") or result.get("id")
    if not post_id:
        raise FacebookPublishError("Meta did not confirm successful post creation")

    # Explicitly request a published Page post, then read back its public-visibility flags.
    # A failed read-back must not cause a retry: the post may already exist on Facebook.
    visibility = _verify_post_visibility(str(post_id), page_access_token, timeout=min(timeout, 20))
    if visibility is None:
        logging.warning("Facebook post %s was created; visibility could not be verified.", post_id)
    else:
        logging.info(
            "Facebook post %s visibility: is_published=%s is_hidden=%s permalink=%s",
            post_id,
            visibility.get("is_published", "unknown"),
            visibility.get("is_hidden", "unknown"),
            visibility.get("permalink_url", "unavailable"),
        )
        if visibility.get("is_published") is False or visibility.get("is_hidden") is True:
            logging.error(
                "Facebook post %s is not publicly visible according to Meta: is_published=%s is_hidden=%s",
                post_id,
                visibility.get("is_published"),
                visibility.get("is_hidden"),
            )
    return str(post_id)
