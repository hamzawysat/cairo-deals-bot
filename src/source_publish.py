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
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() not in APPROVED_IMAGE_HOSTS
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        return None
    return parsed.geturl()


def select_unpublished_candidate(report: dict, state: dict) -> dict | None:
    """Select exactly one new candidate, excluding previously published ASINs/messages."""
    published_ids = {int(value) for value in state.get("published_message_ids", [])}
    published_asins = {str(value).upper() for value in state.get("published_asins", [])}
    for candidate in report.get("candidates", []):
        try:
            message_id = int(candidate["source_message_id"])
            asin = str(candidate["asin"]).upper()
        except (KeyError, TypeError, ValueError):
            continue
        if message_id in published_ids or asin in published_asins:
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
    asins = {str(value).upper() for value in state.get("published_asins", [])}
    message_ids.add(int(candidate["source_message_id"]))
    asins.add(str(candidate["asin"]).upper())
    updated = dict(state)
    updated["published_message_ids"] = sorted(message_ids)[-1000:]
    updated["published_asins"] = sorted(asins)[-1000:]
    return updated
