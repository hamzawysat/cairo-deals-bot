import tempfile
import unittest
from pathlib import Path

from src.processor import (
    build_amazon_affiliate_url,
    extract_single_asin,
    format_repost,
)
from src.storage import SourceStore
from src.original_content import build_original_caption


class ProcessorTests(unittest.TestCase):
    def test_extract_amazon_eg_asin(self):
        self.assertEqual(
            extract_single_asin("عرض https://www.amazon.eg/dp/B0ABC12345?tag=old"),
            "B0ABC12345",
        )

    def test_reject_untrusted_host(self):
        self.assertIsNone(extract_single_asin("https://evil.example/dp/B0ABC12345"))

    def test_reject_ambiguous_multiple_products(self):
        self.assertIsNone(extract_single_asin(
            "https://amazon.eg/dp/B0ABC12345 https://amazon.eg/dp/C0ABC12345"
        ))

    def test_affiliate_url_uses_egypt_tag(self):
        self.assertEqual(
            build_amazon_affiliate_url("B0ABC12345", "cairodeals-21"),
            "https://www.amazon.eg/dp/B0ABC12345?tag=cairodeals-21",
        )

    def test_short_amazon_links_are_not_mistaken_for_verified_asins(self):
        self.assertIsNone(extract_single_asin("https://amzn.to/example-short-link"))

    def test_tracking_tag_is_always_added_to_egypt_product_url(self):
        self.assertEqual(
            build_amazon_affiliate_url("B0ABC12345", "cairodeals-21"),
            "https://www.amazon.eg/dp/B0ABC12345?tag=cairodeals-21",
        )

    def test_caption_preserves_source_facts_and_replaces_link(self):
        result = format_repost(
            "سماعة بلوتوث\nالسعر 250 جنيه\nhttps://amazon.eg/dp/B0ABC12345",
            "cairodeals-21",
        )
        self.assertIsNotNone(result)
        asin, url, caption = result
        self.assertEqual(asin, "B0ABC12345")
        self.assertIn("السعر 250 جنيه", caption)
        self.assertIn(url, caption)
        self.assertNotIn("tag=old", caption)


    def test_original_caption_uses_only_verified_facts_and_tagged_link(self):
        caption = build_original_caption(
            "لمبة LED حمراء 5 ملم - 5 قطع",
            "10.80 جنيه",
            "https://www.amazon.eg/dp/B049WGppS?tag=cairodeals-21",
            "عرض جامد جدًا! أسرعوا قبل انتهاء الفرصة",
        )
        self.assertIsNotNone(caption)
        self.assertIn("لمبة LED حمراء 5 ملم - 5 قطع", caption)
        self.assertIn("10.80 جنيه", caption)
        self.assertIn("tag=cairodeals-21", caption)
        self.assertNotIn("أسرعوا قبل انتهاء الفرصة", caption)

    def test_original_caption_rejects_unverified_or_missing_facts(self):
        self.assertIsNone(build_original_caption(
            "", "10.80 جنيه",
            "https://www.amazon.eg/dp/B049WGppS?tag=cairodeals-21",
        ))
        self.assertIsNone(build_original_caption(
            "لمبة LED", "السعر غير معروف",
            "https://www.amazon.eg/dp/B049WGppS?tag=cairodeals-21",
        ))

    def test_original_caption_rejects_noncanonical_or_untagged_links(self):
        self.assertIsNone(build_original_caption(
            "لمبة LED", "10.80 جنيه", "https://amazon.com/dp/B049WGppS"
        ))


class StorageTests(unittest.TestCase):
    def test_claim_and_duplicate_asin_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SourceStore(str(Path(tmp) / "state.sqlite3"))
            self.assertTrue(store.claim("@amzon44", 100, "B0ABC12345"))
            self.assertFalse(store.claim("@amzon44", 100, "B0ABC12345"))
            store.mark_posted("@amzon44", 100, "tg-1", "fb-1")
            self.assertTrue(store.asin_was_posted("B0ABC12345"))


if __name__ == "__main__":
    unittest.main()
