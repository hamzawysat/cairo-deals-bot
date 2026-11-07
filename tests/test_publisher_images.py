from io import BytesIO
from unittest.mock import Mock, patch

from PIL import Image

from src.publisher import _prepare_full_frame_photo, send_telegram


def _image_bytes(size=(400, 800), color=(220, 30, 30)):
    image = Image.new("RGB", size, color)
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


@patch("src.publisher.requests.get")
def test_prepare_photo_fits_entire_portrait_inside_square(mock_get):
    mock_get.return_value = Mock(content=_image_bytes(), raise_for_status=Mock())
    prepared = _prepare_full_frame_photo("https://images.example/portrait.jpg", 20)
    with Image.open(prepared) as result:
        assert result.size == (1200, 1200)
        assert result.getpixel((10, 600)) == (255, 255, 255)
        assert result.getpixel((600, 200)) != (255, 255, 255)


@patch("src.publisher.requests.post")
@patch("src.publisher.requests.get")
def test_send_telegram_uploads_prepared_full_frame_photo(mock_get, mock_post):
    mock_get.return_value = Mock(content=_image_bytes(), raise_for_status=Mock())
    mock_post.return_value = Mock(
        raise_for_status=Mock(),
        json=Mock(return_value={"ok": True, "result": {"message_id": 123}}),
    )

    message_id = send_telegram(
        "token", "@channel", "caption", photo_url="https://images.example/product.jpg"
    )

    assert message_id == "123"
    _, kwargs = mock_post.call_args
    assert kwargs["files"]["photo"][0] == "product.jpg"
    uploaded = kwargs["files"]["photo"][1]
    with Image.open(uploaded) as image:
        assert image.size == (1200, 1200)
