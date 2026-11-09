"""Performance safeguards for source preview OCR."""
from PIL import Image

from scripts import build_source_offer_previews as preview


def test_image_ocr_uses_sparse_layout_only_as_fallback(tmp_path, monkeypatch):
    image_path = tmp_path / "sample.png"
    Image.new("RGB", (800, 600), "white").save(image_path)
    calls = []

    def fake_ocr(image, *, lang, config):
        calls.append(config)
        return "اسم المنتج ١٠٠ جنيه" if len(calls) == 1 else "fallback"

    monkeypatch.setattr(preview.pytesseract, "image_to_string", fake_ocr)

    result = preview.image_ocr(str(image_path))

    assert result == "اسم المنتج ١٠٠ جنيه"
    assert calls == ["--oem 1 --psm 6"]


def test_ocr_cache_reuses_empty_and_nonempty_results():
    cache = {}
    preview.remember_ocr_text(cache, 101, "اسم المنتج ١٠٠ جنيه")
    preview.remember_ocr_text(cache, 102, "")

    assert preview.cached_ocr_text(cache, 101) == "اسم المنتج ١٠٠ جنيه"
    assert preview.cached_ocr_text(cache, 102) == ""
    assert preview.cached_ocr_text(cache, 103) is None


def test_ocr_cache_is_bounded_and_evicts_oldest_entry():
    cache = {"1": "old"}
    preview.remember_ocr_text(cache, 2, "new", limit=1)

    assert cache == {"2": "new"}


def test_image_ocr_does_not_upscale_small_images_or_exceed_1200px(tmp_path, monkeypatch):
    image_path = tmp_path / "small.png"
    Image.new("RGB", (800, 600), "white").save(image_path)
    seen_sizes = []

    def fake_ocr(image, *, lang, config):
        seen_sizes.append(image.size)
        return "اسم المنتج ١٠٠ جنيه"

    monkeypatch.setattr(preview.pytesseract, "image_to_string", fake_ocr)
    preview.image_ocr(str(image_path))
    assert seen_sizes == [(800, 600)]


def test_image_ocr_downscales_oversized_images_to_1200px(tmp_path, monkeypatch):
    image_path = tmp_path / "large.png"
    Image.new("RGB", (2400, 1200), "white").save(image_path)
    seen_sizes = []

    def fake_ocr(image, *, lang, config):
        seen_sizes.append(image.size)
        return "اسم المنتج ١٠٠ جنيه"

    monkeypatch.setattr(preview.pytesseract, "image_to_string", fake_ocr)
    preview.image_ocr(str(image_path))
    assert seen_sizes == [(1200, 600)]


def test_preview_state_preserves_facebook_interval_and_other_publisher_fields():
    prior_state = {
        "last_facebook_publish_at": 1794190000.5,
        "platform_status": {"123": {"telegram": "456"}},
        "published_message_ids": [123],
        "publisher_extension": {"keep": True},
    }

    updated = preview.merge_preview_state(
        prior_state,
        last_seen_message_id=200,
        pending_candidates=[{"source_message_id": 201}],
        ocr_cache={"201": "cached OCR"},
    )

    assert updated["last_facebook_publish_at"] == 1794190000.5
    assert updated["publisher_extension"] == {"keep": True}
    assert updated["platform_status"] == {"123": {"telegram": "456"}}
    assert updated["published_message_ids"] == [123]
    assert updated["last_seen_message_id"] == 200
    assert updated["pending_candidates"] == [{"source_message_id": 201}]
    assert updated["ocr_cache"] == {"201": "cached OCR"}
