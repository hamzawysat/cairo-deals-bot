from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image

from src.telegram_product_card import (
    _ImageParser,
    _valid_image_url,
    create_telegram_product_card,
    find_amazon_product_image,
    _load_product_image,
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
        assert card.getpixel((540, 500)) != (23, 52, 90)


def test_card_rejects_invalid_product_details(tmp_path):
    with pytest.raises(ValueError, match="invalid"):
        create_telegram_product_card(
            asin="B0ABC12345",
            product_name="",
            price="125 جنيه",
            image_url="https://m.media-amazon.com/images/I/example.jpg",
            output_path=tmp_path / "bad.jpg",
        )


def test_caption_changes_only_presentation_and_keeps_original_links():
    from scripts.publish_pending_source_offers import _rebuild_caption

    candidate = {
        "product_name_source": "زيت عباد الشمس",
        "advertised_price": "432 جنيه",
        "affiliate_url": "https://www.amazon.eg/dp/B0ABC12345?tag=cairodeals-21",
    }
    telegram = _rebuild_caption(candidate, for_telegram=True)
    facebook = _rebuild_caption(candidate, for_telegram=False)

    assert "زيت عباد الشمس" in telegram
    assert "432 جنيه" in telegram
    assert "\n\n" in telegram
    assert candidate["affiliate_url"] in telegram
    assert candidate["affiliate_url"] in facebook
    assert "https://t.me/cairo_deals" in telegram
    assert "https://www.facebook.com/share/19hQqVpCuG/" in facebook



def test_amazon_page_parser_reads_product_title_span_and_dynamic_image():
    parser = _ImageParser()
    parser.feed(
        '<span id="productTitle">منتج أمازون تجريبي</span>'
        '<img data-a-dynamic-image="{&quot;https://m.media-amazon.com/images/I/item.jpg&quot;:[800,800]}">'
    )
    assert parser.title == "منتج أمازون تجريبي"
    assert parser.image_url == "https://m.media-amazon.com/images/I/item.jpg"



def test_image_loader_waits_and_retries_until_complete_image(monkeypatch):
    import io
    import src.telegram_product_card as cards

    buffer = io.BytesIO()
    Image.new("RGB", (640, 480), "white").save(buffer, format="PNG")
    complete_image = buffer.getvalue()

    def response(payload):
        item = Mock()
        item.headers = {"Content-Type": "image/png"}
        item.raise_for_status = Mock()
        item.iter_content.return_value = [payload]
        return item

    session = Mock()
    session.get.side_effect = [response(b"partial-image"), response(complete_image)]
    sleeps = []
    monkeypatch.setattr(cards.time, "sleep", lambda seconds: sleeps.append(seconds))

    image = _load_product_image(
        "https://m.media-amazon.com/images/I/example.jpg",
        session=session,
    )

    assert image.size == (640, 480)
    assert session.get.call_count == 2
    assert sleeps == [cards.IMAGE_READY_DELAY_SECONDS, cards.IMAGE_RETRY_DELAY_SECONDS]
