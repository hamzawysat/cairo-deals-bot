from unittest.mock import Mock, patch

import pytest

from src.facebook_publisher import BufferPublishError, send_facebook


def _success_response():
    return Mock(
        raise_for_status=Mock(),
        json=Mock(return_value={
            "data": {
                "createPost": {
                    "post": {
                        "id": "buffer-post-123",
                        "status": "sent",
                        "sharedNow": True,
                    }
                }
            }
        }),
    )


@patch("src.facebook_publisher.requests.post")
def test_facebook_uses_immediate_publish_and_public_image(mock_post):
    mock_post.return_value = _success_response()

    post_id = send_facebook(
        "test-api-key",
        "facebook-channel-id",
        "Test offer",
        "https://images.example/product.jpg",
    )

    assert post_id == "buffer-post-123"
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.buffer.com"
    assert kwargs["headers"]["Authorization"] == "Bearer test-api-key"
    variables = kwargs["json"]["variables"]["input"]
    assert variables["channelId"] == "facebook-channel-id"
    assert variables["mode"] == "shareNow"
    assert variables["schedulingType"] == "automatic"
    assert variables["metadata"] == {"facebook": {"type": "post"}}
    assert variables["assets"] == [
        {"image": {"url": "https://images.example/product.jpg"}}
    ]


@patch("src.facebook_publisher.requests.post")
def test_facebook_supports_text_only_posts(mock_post):
    mock_post.return_value = _success_response()

    send_facebook("test-api-key", "facebook-channel-id", "Text only")

    variables = mock_post.call_args.kwargs["json"]["variables"]["input"]
    assert variables["assets"] == []
    assert variables["metadata"]["facebook"]["type"] == "post"


def test_facebook_requires_credentials():
    with pytest.raises(BufferPublishError, match="API key"):
        send_facebook("", "facebook-channel-id", "Test")


def test_facebook_rejects_non_https_image():
    with pytest.raises(BufferPublishError, match="HTTPS"):
        send_facebook("test-api-key", "facebook-channel-id", "Test", "http://bad.example/image.jpg")


@patch("src.facebook_publisher.requests.post")
def test_facebook_reports_graphql_errors(mock_post):
    mock_post.return_value = Mock(
        raise_for_status=Mock(),
        json=Mock(return_value={"errors": [{"message": "Permission denied"}]}),
    )

    with pytest.raises(BufferPublishError, match="Permission denied"):
        send_facebook("test-api-key", "facebook-channel-id", "Test")
