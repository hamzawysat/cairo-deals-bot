import json
from unittest.mock import Mock, patch

from src.publisher import send_telegram


@patch("src.publisher.requests.post")
def test_telegram_uses_link_preview_instead_of_uploading_product_photo(mock_post):
    mock_post.return_value = Mock(
        raise_for_status=Mock(),
        json=Mock(return_value={"ok": True, "result": {"message_id": 456}}),
    )

    message_id = send_telegram(
        "token",
        "@channel",
        "🛍️ منتج\n💰 100 جنيه\n👇 https://link.amazon/B0example",
    )

    assert message_id == "456"
    args, kwargs = mock_post.call_args
    assert args[0].endswith("/sendMessage")
    assert json.loads(kwargs["data"]["link_preview_options"]) == {
        "prefer_small_media": True,
        "show_above_text": False,
    }
    assert "files" not in kwargs
