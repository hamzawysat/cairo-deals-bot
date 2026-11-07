"""Facebook publishing through Buffer's GraphQL API.

This module is deliberately independent from the Telegram publisher.
"""
import requests


BUFFER_API_URL = "https://api.buffer.com"
CREATE_POST_MUTATION = """
mutation PublishFacebookPost($input: CreatePostInput!) {
  createPost(input: $input) {
    ... on PostActionSuccess {
      post {
        id
        status
        sharedNow
      }
    }
    ... on MutationError {
      message
    }
  }
}
"""


class BufferPublishError(RuntimeError):
    """Buffer rejected the Facebook post or could not be reached."""


def send_facebook(
    api_key: str,
    channel_id: str,
    text: str,
    photo_url: str | None = None,
    timeout: int = 30,
) -> str:
    """Publish one post immediately to the configured Buffer channel."""
    if not api_key:
        raise BufferPublishError("Buffer API key is missing")
    if not channel_id:
        raise BufferPublishError("Buffer Facebook channel ID is missing")
    if not text or not text.strip():
        raise BufferPublishError("Facebook post text is empty")
    if photo_url and not photo_url.startswith("https://"):
        raise BufferPublishError("Facebook image URL must use HTTPS")

    assets = []
    if photo_url:
        assets.append({"image": {"url": photo_url}})

    payload = {
        "query": CREATE_POST_MUTATION,
        "variables": {
            "input": {
                "channelId": channel_id,
                "text": text,
                "assets": assets,
                "schedulingType": "automatic",
                "mode": "shareNow",
                "needsApproval": False,
            }
        },
    }

    try:
        response = requests.post(
            BUFFER_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        result = response.json()
    except requests.RequestException as exc:
        raise BufferPublishError(f"Buffer request failed: {exc}") from exc
    except ValueError as exc:
        raise BufferPublishError("Buffer returned invalid JSON") from exc

    if result.get("errors"):
        messages = "; ".join(
            str(item.get("message", "GraphQL error"))
            for item in result["errors"]
        )
        raise BufferPublishError(messages)

    action = (result.get("data") or {}).get("createPost") or {}
    if action.get("message"):
        raise BufferPublishError(str(action["message"]))

    post = action.get("post") or {}
    post_id = post.get("id")
    if not post_id:
        raise BufferPublishError("Buffer did not confirm successful post creation")
    return str(post_id)
