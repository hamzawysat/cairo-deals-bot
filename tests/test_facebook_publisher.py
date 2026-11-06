from io import BytesIO
from unittest.mock import Mock, patch

from PIL import Image

from src.facebook_publisher import publish_facebook_photo
from src.publisher import PublishError


def _image_bytes(size=(400, 800), color=(220, 30, 30)):
    image = Image.new("RGB", size, color)
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


@patch("src.publisher.requests.get")
@patch("src.facebook_publisher.requests.post")
def test_publish_facebook_photo_uploads_full_frame_image(mock_post, mock_get):
    mock_get.return_value = Mock(content=_image_bytes(), raise_for_status=Mock())
    mock_post.return_value = Mock(
        ok=True,
        json=Mock(return_value={"id": "page_123_post_456"}),
    )

    post_id = publish_facebook_photo(
        "123456",
        "page-token",
        "Product caption",
        "https://images.example/product.jpg",
    )

    assert post_id == "page_123_post_456"
    args, kwargs = mock_post.call_args
    assert args[0] == "https://graph.facebook.com/v26.0/123456/photos"
    assert kwargs["data"]["caption"] == "Product caption"
    assert kwargs["data"]["published"] == "true"
    assert kwargs["data"]["access_token"] == "page-token"
    uploaded = kwargs["files"]["source"][1]
    with Image.open(uploaded) as image:
        assert image.size == (1200, 1200)
        assert image.getpixel((10, 600)) == (255, 255, 255)


def test_facebook_publisher_rejects_missing_credentials():
    try:
        publish_facebook_photo("", "", "caption", "https://images.example/product.jpg")
        assert False, "Expected PublishError"
    except PublishError as exc:
        assert "Page ID" in str(exc)


def test_facebook_publisher_rejects_non_https_image():
    try:
        publish_facebook_photo("123", "token", "caption", "http://images.example/a.jpg")
        assert False, "Expected PublishError"
    except PublishError as exc:
        assert "HTTPS" in str(exc)


@patch("src.publisher.requests.get")
@patch("src.facebook_publisher.requests.post")
def test_facebook_api_error_is_reported_without_success(mock_post, mock_get):
    mock_get.return_value = Mock(content=_image_bytes(), raise_for_status=Mock())
    mock_post.return_value = Mock(
        ok=False,
        text='{"error":{"message":"Permission denied","code":200}}',
        json=Mock(return_value={"error": {"message": "Permission denied", "code": 200}}),
    )

    try:
        publish_facebook_photo(
            "123", "token", "caption", "https://images.example/product.jpg"
        )
        assert False, "Expected PublishError"
    except PublishError as exc:
        assert "Permission denied" in str(exc)
        assert "200" in str(exc)
