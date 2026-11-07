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
    assert kwargs["data"]["link_preview_options"] == (
        '{"prefer_small_media":true,"show_above_text":false}'
    )
    assert "text" in kwargs["data"]
    assert "files" not in kwargs
    assert "photo" not in kwargs


@patch("src.publisher.requests.get")
def test_amazon_short_link_expands_to_direct_amazon_eg_product(mock_get):
    from src.publisher import resolve_amazon_product_url

    response = Mock(
        url="https://www.amazon.eg/dp/B0iUJDVt8?ref_=share",
        raise_for_status=Mock(),
        close=Mock(),
    )
    mock_get.return_value = response

    result = resolve_amazon_product_url(
        "https://link.amazon/B0iUJDVt8", "cairodeals-21"
    )

    assert result == (
        "https://www.amazon.eg/dp/B0iUJDVt8?ref_=share&tag=cairodeals-21"
    )
    mock_get.assert_called_once()
    assert mock_get.call_args.kwargs["allow_redirects"] is True


@patch("src.publisher.requests.get")
def test_amazon_short_link_refuses_amzlinks_intermediate_destination(mock_get):
    import pytest
    from src.publisher import (
        AmazonLinkResolutionError,
        resolve_amazon_product_url,
    )

    response = Mock(
        url="https://amzlinks.in/some-intermediate-page",
        raise_for_status=Mock(),
        close=Mock(),
    )
    mock_get.return_value = response

    with pytest.raises(AmazonLinkResolutionError, match="did not resolve directly"):
        resolve_amazon_product_url(
            "https://link.amazon/B0iUJDVt8", "cairodeals-21"
        )
