import json
import re
from pathlib import Path


def test_all_published_offer_copy_is_arabic_only():
    offers = json.loads((Path(__file__).resolve().parents[1] / "data" / "offers.json").read_text(encoding="utf-8"))
    english_letters = re.compile(r"[A-Za-z]")
    for offer in offers:
        public_copy = [
            offer.get("title", ""),
            offer.get("description", ""),
            *(offer.get("features") or []),
            *(offer.get("hashtags") or []),
        ]
        assert all(not english_letters.search(value) for value in public_copy), offer.get("id")


def test_amazon_search_terms_remain_unchanged_and_can_stay_english():
    offers = json.loads((Path(__file__).resolve().parents[1] / "data" / "offers.json").read_text(encoding="utf-8"))
    by_id = {offer["id"]: offer for offer in offers}
    assert by_id["amazon-redmi-15c-8-256-002"]["search_terms"] == "Xiaomi Redmi 15C 8GB 256GB"
    assert by_id["amazon-redragon-gs522-speakers-003"]["search_terms"] == "Redragon GS522 Cipher RGB Computer Speakers"
