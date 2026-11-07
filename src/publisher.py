"""Telegram text publishing with automatic link previews enabled."""
import requests
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


class PublishError(RuntimeError):
    pass


class AmazonLinkResolutionError(PublishError):
    """The short link did not resolve to a usable Amazon Egypt product page."""


def resolve_amazon_product_url(url: str, tracking_id: str, timeout: int = 15) -> str:
    """Expand Amazon short links so Telegram previews the actual product page."""
    parsed = urlparse(str(url or "").strip())
    allowed_short_hosts = {"link.amazon", "amzn.to"}
    allowed_store_hosts = {"amazon.eg", "www.amazon.eg"}

    if parsed.scheme != "https" or not parsed.hostname:
        raise AmazonLinkResolutionError("Amazon URL must use HTTPS")

    if parsed.hostname in allowed_store_hosts:
        final_url = url
    elif parsed.hostname in allowed_short_hosts:
        try:
            response = requests.get(
                url,
                allow_redirects=True,
                stream=True,
                timeout=timeout,
                headers={"User-Agent": "Mozilla/5.0 (compatible; CairoDealsBot/1.0)"},
            )
            try:
                response.raise_for_status()
                final_url = response.url
            finally:
                response.close()
        except requests.RequestException as exc:
            raise AmazonLinkResolutionError(
                f"Could not expand Amazon short link: {exc}"
            ) from exc
    else:
        raise AmazonLinkResolutionError("Link is not an Amazon Egypt product URL")

    destination = urlparse(final_url)
    if destination.scheme != "https" or destination.hostname not in allowed_store_hosts:
        raise AmazonLinkResolutionError(
            f"Short link did not resolve directly to Amazon Egypt (resolved host: {destination.hostname or 'unknown'})"
        )
    if not destination.path or destination.path == "/":
        raise AmazonLinkResolutionError("Resolved URL is not a product page")
    if not tracking_id:
        raise AmazonLinkResolutionError("Amazon tracking ID is missing")

    query = dict(parse_qsl(destination.query, keep_blank_values=True))
    query["tag"] = tracking_id
    return urlunparse(destination._replace(query=urlencode(query)))


def send_telegram(
    token: str,
    channel_id: str,
    text: str,
    timeout: int = 20,
) -> str:
    """Send text only and leave Telegram's automatic URL preview enabled."""
    if not token or not channel_id:
        raise PublishError("Telegram credentials are missing")

    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={
            "chat_id": channel_id,
            "text": text,
            "disable_web_page_preview": False,
            "link_preview_options": '{"prefer_small_media":true,"show_above_text":false}',
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise PublishError(payload.get("description", "Telegram rejected the message"))
    return str(payload["result"]["message_id"])
