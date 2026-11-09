from unittest.mock import Mock, patch
import pytest
from src.facebook_publisher import FacebookPublishError, get_page_identity, send_facebook


def identity():
    return Mock(raise_for_status=Mock(), json=Mock(return_value={"id": "12345", "name": "cairodeals"}))


def published():
    return Mock(raise_for_status=Mock(), json=Mock(return_value={"id": "12345_67890"}))


def visible_post():
    return Mock(
        raise_for_status=Mock(),
        json=Mock(return_value={
            "id": "12345_67890",
            "is_published": True,
            "is_hidden": False,
            "permalink_url": "https://www.facebook.com/12345/posts/67890",
        }),
    )


@patch("src.facebook_publisher.requests.post")
@patch("src.facebook_publisher.requests.get")
def test_photo_post_to_validated_page(mock_get, mock_post, monkeypatch):
    monkeypatch.setenv("META_PAGE_NAME", "cairodeals")
    mock_get.side_effect, mock_post.return_value = [identity(), visible_post()], published()
    assert send_facebook("page-token", "Test offer", "https://images.example/product.jpg") == "12345_67890"
    assert mock_post.call_args.args[0].endswith("/12345/photos")
    assert mock_post.call_args.kwargs["data"]["caption"] == "Test offer"
    assert mock_post.call_args.kwargs["data"]["published"] == "true"
    assert mock_get.call_args.kwargs["params"]["fields"] == "id,is_published,is_hidden,permalink_url"


@patch("src.facebook_publisher.requests.post")
@patch("src.facebook_publisher.requests.get")
def test_text_post_to_page(mock_get, mock_post, monkeypatch):
    monkeypatch.setenv("META_PAGE_NAME", "cairodeals")
    mock_get.side_effect, mock_post.return_value = [identity(), visible_post()], published()
    send_facebook("page-token", "Text only")
    assert mock_post.call_args.args[0].endswith("/12345/feed")
    assert mock_post.call_args.kwargs["data"]["message"] == "Text only"
    assert mock_post.call_args.kwargs["data"]["published"] == "true"


def test_token_required():
    with pytest.raises(FacebookPublishError, match="token"):
        send_facebook("", "Test")


@patch("src.facebook_publisher.requests.get")
def test_rejects_wrong_page(mock_get, monkeypatch):
    monkeypatch.setenv("META_PAGE_NAME", "cairodeals")
    mock_get.return_value = Mock(raise_for_status=Mock(), json=Mock(return_value={"id": "1", "name": "Personal profile"}))
    with pytest.raises(FacebookPublishError, match="expected Page"):
        get_page_identity("user-token")


def test_rejects_non_https_image():
    with pytest.raises(FacebookPublishError, match="HTTPS"):
        send_facebook("page-token", "Test", "http://bad.example/image.jpg")
