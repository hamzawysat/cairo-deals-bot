from datetime import datetime, timezone

from src.main import _eligible_offers, _interval_wait_seconds


def test_scheduler_grace_covers_early_cron_tick():
    last = "2026-11-06 20:55:19"
    now = datetime(2026, 11, 6, 21, 0, 15, tzinfo=timezone.utc)
    assert _interval_wait_seconds(last, now, interval_minutes=5, grace_seconds=60) == 0


def test_scheduler_still_waits_when_early_by_more_than_grace():
    last = "2026-11-06 20:55:19"
    now = datetime(2026, 11, 6, 20, 59, 18, tzinfo=timezone.utc)
    assert _interval_wait_seconds(last, now, interval_minutes=5, grace_seconds=60) == 1


def test_two_hour_interval_does_not_miss_due_to_seconds_jitter():
    last = "2026-11-06 10:00:19"
    now = datetime(2026, 11, 6, 12, 0, 0, tzinfo=timezone.utc)
    assert _interval_wait_seconds(last, now, interval_minutes=120, grace_seconds=60) == 0


def test_offer_without_https_image_is_skipped():
    offers = [{
        "id": "paper-1",
        "store": "amazon_eg",
        "title": "ورق تصوير",
        "affiliate_url": "https://www.amazon.eg/dp/example",
        "image_url": "",
        "price_egp": 100,
        "enabled": True,
    }]
    settings = {
        "stores": {"amazon_eg": {"enabled": True}},
        "safety": {"skip_missing_price": True, "require_image": True},
    }
    assert _eligible_offers(offers, settings) == []


def test_offer_with_https_image_remains_eligible():
    offer = {
        "id": "paper-2",
        "store": "amazon_eg",
        "title": "ورق تصوير",
        "affiliate_url": "https://www.amazon.eg/dp/example",
        "image_url": "https://images.example.com/paper.jpg",
        "price_egp": 100,
        "enabled": True,
    }
    settings = {
        "stores": {"amazon_eg": {"enabled": True}},
        "safety": {"skip_missing_price": True, "require_image": True},
    }
    assert [item[0]["id"] for item in _eligible_offers([offer], settings)] == ["paper-2"]
