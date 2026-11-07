import json
import sqlite3
from unittest.mock import Mock

import requests

from src import main as main_module
from src.product_availability import (
    AVAILABLE,
    UNKNOWN,
    UNAVAILABLE,
    check_amazon_offer_availability,
    classify_amazon_product_page,
)


def test_classifies_jsonld_in_stock():
    html = '<script type="application/ld+json">{"@type":"Product","offers":{"availability":"https://schema.org/InStock"}}</script>'
    assert classify_amazon_product_page(html) == AVAILABLE


def test_classifies_jsonld_out_of_stock():
    html = '<script type="application/ld+json">{"offers":{"availability":"https://schema.org/OutOfStock"}}</script>'
    assert classify_amazon_product_page(html) == UNAVAILABLE


def test_classifies_visible_unavailable_text_and_unknown_pages():
    assert classify_amazon_product_page("<div>Currently unavailable</div>") == UNAVAILABLE
    assert classify_amazon_product_page("<html><body>Robot check</body></html>") == UNKNOWN


def test_short_link_is_resolved_and_original_link_is_not_changed():
    response = Mock()
    response.url = "https://www.amazon.eg/dp/B0C1234567?tag=cairodeals-21"
    response.text = '<script type="application/ld+json">{"offers":{"availability":"https://schema.org/InStock"}}</script>'
    session = Mock()
    session.get.return_value = response
    offer = {"store": "amazon_eg", "affiliate_url": "https://link.amazon/B0C1234567"}

    status, detail = check_amazon_offer_availability(offer, session=session)

    assert status == AVAILABLE
    assert "B0C1234567" in detail
    assert offer["affiliate_url"] == "https://link.amazon/B0C1234567"
    session.get.assert_called_once_with(
        "https://link.amazon/B0C1234567",
        allow_redirects=True,
        timeout=15,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; CairoDealsBot/1.0)",
            "Accept-Language": "ar-EG,ar;q=0.9,en;q=0.8",
        },
    )


def test_blocked_or_unresolvable_amazon_page_is_unknown_not_assumed_available():
    session = Mock()
    session.get.side_effect = requests.Timeout()
    status, _ = check_amazon_offer_availability(
        {"store": "amazon_eg", "affiliate_url": "https://amzn.to/example"},
        session=session,
    )
    assert status == UNKNOWN


def test_run_once_skips_unavailable_amazon_offer_and_uses_next(tmp_path, monkeypatch, capsys):
    settings = {
        "dry_run": False,
        "interval_minutes": 5,
        "max_posts_per_run": 1,
        "channels": {"telegram": {"enabled": True}},
        "stores": {},
    }
    offers = [
        {"id": "out-of-stock", "store": "amazon_eg", "title": "غير متاح", "affiliate_url": "https://amzn.to/a", "image_url": "https://img.example/a.jpg"},
        {"id": "in-stock", "store": "amazon_eg", "title": "متاح", "affiliate_url": "https://amzn.to/b", "image_url": "https://img.example/b.jpg"},
    ]
    monkeypatch.setattr(main_module, "load_json", lambda path: settings if str(path).endswith("settings.json") else offers)
    monkeypatch.setattr(
        main_module,
        "_eligible_offers",
        lambda loaded, cfg: [(offers[0], offers[0]["affiliate_url"]), (offers[1], offers[1]["affiliate_url"])],
    )
    statuses = iter([(UNAVAILABLE, "out of stock"), (AVAILABLE, "in stock")])
    monkeypatch.setattr(main_module, "check_amazon_offer_availability", lambda offer: next(statuses))
    db_path = tmp_path / "state.sqlite3"
    monkeypatch.setattr(main_module, "DB_PATH", db_path)
    sent = []
    monkeypatch.setattr(main_module, "send_telegram", lambda *args, **kwargs: sent.append(kwargs["photo_url"]) or "msg-1")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@test-channel")

    main_module.run_once()

    output = capsys.readouterr().out
    assert "SKIP out-of-stock: Amazon availability UNAVAILABLE" in output
    assert "POSTED in-stock" in output
    assert sent == ["https://img.example/b.jpg"]
    with sqlite3.connect(db_path) as db:
        posted = db.execute("SELECT offer_id FROM rotation_posts").fetchall()
    assert posted == [("in-stock",)]
