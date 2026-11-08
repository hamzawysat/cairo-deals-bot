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
