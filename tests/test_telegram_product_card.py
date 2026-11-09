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



def test_buybox_price_overrides_stale_meta_price():
    parser = _ImageParser()
    parser.feed(
        '<meta property="product:price:amount" content="621">'
        '<div id="corePrice_feature_div">'
        '<span class="a-price"><span class="a-offscreen">754.00 جنيه</span></span>'
        '</div>'
    )
    assert parser.price == "754.00 جنيه"
    assert parser.price_source == "corePrice_feature_div"


def test_buybox_ignores_strikethrough_and_installment_prices_outside_buybox():
    parser = _ImageParser()
    parser.feed(
        '<span class="a-price a-text-price"><span class="a-offscreen">900.00 جنيه</span></span>'
        '<div id="corePrice_feature_div">'
        '<span class="a-price"><span class="a-offscreen">754.00 جنيه</span></span>'
        '</div>'
        '<div id="installmentPrice">188.50 جنيه شهريًا</div>'
    )
    assert parser.price == "754.00 جنيه"


def test_meta_is_fallback_only_when_buybox_is_absent():
    parser = _ImageParser()
    parser.feed('<meta property="product:price:amount" content="621">')
    assert parser.price == "621"
    assert parser.price_source is None


def test_buybox_can_be_extracted_from_apex_price_to_pay():
    parser = _ImageParser()
    parser.feed(
        '<div class="apexPriceToPay">'
        '<span class="a-offscreen">754.00 جنيه</span>'
        '</div>'
    )
    assert parser.price == "754.00 جنيه"
    assert parser.price_source == "apexPriceToPay"


def test_amazon_page_parser_reads_product_title_span_and_dynamic_image():