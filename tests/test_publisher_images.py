from unittest.mock import Mock, patch

from src.publisher import send_telegram


@patch("src.publisher.requests.post")
def test_send_telegram_uses_text_and_keeps_automatic_link_preview(mock_post):
    mock_post.return_value = Mock(
        raise_for_status=Mock(),
        json=Mock(return_value={"ok": True, "result": {"message_id": 123}}),
    )

    message_id = send_telegram(
        "token",
        "@channel",
        "🛍️ منتج\n💰 105 جنيه\n👇 https://link.amazon/example",
    )

    assert message_id == "123"
    args, kwargs = mock_post.call_args
    assert args[0].endswith("/sendMessage")
    assert kwargs["data"]["disable_web_page_preview"] is False
    assert "text" in kwargs["data"]
    assert "files" not in kwargs
    assert "photo" not in kwargs
