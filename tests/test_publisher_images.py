import json
from unittest.mock import Mock, patch

from src.publisher import send_telegram


@patch("src.publisher.requests.post")
def test_send_telegram_uses_send_message_and_enables_automatic_link_preview(mock_post):
    mock_post.return_value = Mock(
        raise_for_status=Mock(),
        json=Mock(return_value={"ok": True, "result": {"message_id": 123}}),
    )

    message_id = send_telegram(
        "token",
        "@channel",
        "🍓 مربى ميرو\n💰 105 جنيه بدل 118 جنيه - خصم 11%\n👇 https://link.amazon/B0iUJDVt8",
    )

    assert message_id == "123"
    args, kwargs = mock_post.call_args
    assert args[0].endswith("/sendMessage")
    assert json.loads(kwargs["data"]["link_preview_options"]) == {
        "prefer_small_media": True,
        "show_above_text": False,
    }
    assert kwargs["data"]["text"].endswith("https://link.amazon/B0iUJDVt8")
    assert "files" not in kwargs
