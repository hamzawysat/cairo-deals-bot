from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image

from src.telegram_product_card import (
    _ImageParser,
    _valid_image_url,
    create_telegram_product_card,
    find_amazon_product_image,
)


def test_only_amazon_image_cdn_urls_are_accepted():
    assert _valid_image_url("https://m.media-amazon.com/images/I/example.jpg")
    assert not _valid_image_url("https://evil.example/image.jpg")
    assert not _valid_image_url("http://m.media-amazon.com/image.jpg")
    assert not _valid_image_url("https://m.media-amazon.com.evil.example/image.jpg")


def test_amazon_page_parser_reads_open_graph_image():
    parser = _ImageParser()
    parser.feed('<meta property="og:image" content="https://m.media-amazon.com/images/I/item.jpg">')
    assert parser.image_url == "https://m.media-amazon.com/images/I/item.jpg"


def test_product_image_url_must_come_from_amazon_cdn():
    response = Mock()
    response.text = '<meta property="og:image" content="https://evil.example/item.jpg">'
    response.raise_for_status = Mock()
    session = Mock()
    session.get.return_value = response
    with pytest.raises(ValueError, match="approved Amazon CDN"):
        find_amazon_product_image("B0ABC12345", session=session)


def test_card_is_vertical_and_keeps_product_image_inside(tmp_path, monkeypatch):
    import src.telegram_product_card as cards

    product = Image.new("RGB", (1600, 500), "white")
    monkeypatch.setattr(cards, "_load_product_image", lambda url, session=None: product.copy())
    output = tmp_path / "telegram-card.jpg"
    result = create_telegram_product_card(
        asin="B0ABC12345",
        product_name="منتج تجريبي",
        price="125 جنيه",
        image_url="https://m.media-amazon.com/images/I/example.jpg",
        output_path=output,
    )
    assert result == output
    with Image.open(output) as card:
        assert card.size == (1080, 1350)
        # The wide source image must remain contained rather than stretched/cropped.
        assert card.getpixel((540, 480)) != (32, 33, 36)


def test_card_rejects_invalid_product_details(tmp_path):
    with pytest.raises(ValueError, match="invalid"):
        create_telegram_product_card(
            asin="B0ABC12345",
            product_name="",
            price="125 جنيه",
            image_url="https://m.media-amazon.com/images/I/example.jpg",
            output_path=tmp_path / "bad.jpg",
        )
