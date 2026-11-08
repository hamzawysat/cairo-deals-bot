"""Safety gates and state helpers for one-at-a-time source publishing."""
from __future__ import annotations

from urllib.parse import urlparse

APPROVED_IMAGE_HOSTS = {
    "m.media-amazon.com",
    "images-na.ssl-images-amazon.com",
    "images-eu.ssl-images-amazon.com",
}


def validate_approved_image_record(record: dict | None) -> str | None:
    """Require explicit reuse permission and an HTTPS image on a known Amazon CDN."""
    if not isinstance(record, dict) or record.get("rights_confirmed") is not True:
        return None
    rights_source = str(record.get("rights_source") or "").strip()
    if len(rights_source) < 8:
        return None
    try:
        parsed = urlparse(str(record.get("url") or "").strip())
        valid_port = parsed.port in (None, 443)
        host = (parsed.hostname or "").lower()
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or host not in APPROVED_IMAGE_HOSTS
        or parsed.username
        or parsed.password
        or not valid_port
    ):
        return None
    return parsed.geturl()


def select_unpublished_candidate(report: dict, state: dict) -> dict | None:
    """Select a candidate unless this exact source message was fully published."""
    published_ids = {int(value) for value in state.get("published_message_ids", [])}
    for candidate in report.get("candidates", []):
        try:
            message_id = int(candidate["source_message_id"])
            asin = str(candidate["asin"]).upper()
        except (KeyError, TypeError, ValueError):
            continue
        status = state.get("platform_status", {}).get(str(message_id), {})
        if message_id in published_ids or (status.get("facebook") and status.get("telegram")):
            continue
        if candidate.get("publishing_performed") is not False:
            continue
        if not candidate.get("affiliate_url") or not candidate.get("caption_preview"):
            continue
        return candidate
    return None


def mark_candidate_published(state: dict, candidate: dict) -> dict:
    """Return updated dedupe state after the destination confirms delivery."""
    message_ids = {int(value) for value in state.get("published_message_ids", [])}
    message_ids.add(int(candidate["source_message_id"]))
    updated = dict(state)
    updated["published_message_ids"] = sorted(message_ids)[-1000:]
    return updated


def mark_platform_published(state: dict, candidate: dict, platform: str, remote_id: str) -> dict:
    """Persist one destination confirmation independently for safe partial retries."""
    if platform not in {"telegram", "facebook"}:
        raise ValueError("Unsupported publishing platform")
    updated = dict(state)
    statuses = dict(updated.get("platform_status", {}))
    key = str(candidate["source_message_id"])
    item = dict(statuses.get(key, {}))
    item[platform] = str(remote_id)
    item["asin"] = str(candidate["asin"]).upper()
    statuses[key] = item
    updated["platform_status"] = statuses
    if item.get("telegram") and item.get("facebook"):
        message_ids = {int(value) for value in updated.get("published_message_ids", [])}
        message_ids.add(int(candidate["source_message_id"]))
        updated["published_message_ids"] = sorted(message_ids)[-1000:]
    return updated
