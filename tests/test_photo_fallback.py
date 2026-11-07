import sqlite3
from unittest.mock import Mock, patch

import pytest
import requests

from src import main as main_module
from src.publisher import PhotoPreparationError, _prepare_full_frame_photo


def test_blocked_image_http_403_is_reported_as_photo_preparation_error():
    response = Mock()
    response.raise_for_status.side_effect = requests.HTTPError("403 Client Error: Forbidden")
    with patch("src.publisher.requests.get", return_value=response):
        with pytest.raises(PhotoPreparationError, match="Could not download product image"):
            _prepare_full_frame_photo("https://blocked.example/product.jpg", 20)


def test_run_once_skips_blocked_product_image_and_publishes_next(tmp_path, monkeypatch, capsys):
    settings = {
        "dry_run": False,
        "interval_minutes": 5,
        "max_posts_per_run": 1,
        "channels": {"telegram": {"enabled": True}},
        "stores": {},
    }
    offers = [
        {"id": "blocked-photo", "title": "صورة محظورة", "image_url": "https://blocked.example/a.jpg"},
        {"id": "good-photo", "title": "صورة سليمة", "image_url": "https://good.example/b.jpg"},
    ]
    monkeypatch.setattr(main_module, "load_json", lambda path: settings if str(path).endswith("settings.json") else offers)
    monkeypatch.setattr(
        main_module,
        "_eligible_offers",
        lambda loaded, cfg: [(offers[0], "https://shop.example/1"), (offers[1], "https://shop.example/2")],
    )
    db_path = tmp_path / "state.sqlite3"
    monkeypatch.setattr(main_module, "DB_PATH", db_path)
    calls = []

    def fake_send(token, channel, caption, photo_url=None):
        calls.append(photo_url)
        if photo_url and "blocked" in photo_url:
            raise PhotoPreparationError("403 Forbidden")
        return "telegram-message-2"

    monkeypatch.setattr(main_module, "send_telegram", fake_send)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@test-channel")

    main_module.run_once()

    output = capsys.readouterr().out
    assert "SKIP blocked-photo" in output
    assert "POSTED good-photo" in output
    assert calls == [offers[0]["image_url"], offers[1]["image_url"]]
    with sqlite3.connect(db_path) as db:
        posted = db.execute("SELECT offer_id, message_id FROM rotation_posts").fetchall()
    assert posted == [("good-photo", "telegram-message-2")]


def test_run_once_advances_cycle_when_only_unused_offer_has_blocked_image(tmp_path, monkeypatch, capsys):
    settings = {
        "dry_run": False,
        "interval_minutes": 5,
        "max_posts_per_run": 1,
        "channels": {"telegram": {"enabled": True}},
        "stores": {},
    }
    offers = [
        {"id": "blocked-photo", "title": "صورة محظورة", "image_url": "https://blocked.example/a.jpg"},
        {"id": "previously-used-good-photo", "title": "صورة سليمة", "image_url": "https://good.example/b.jpg"},
    ]
    monkeypatch.setattr(main_module, "load_json", lambda path: settings if str(path).endswith("settings.json") else offers)
    monkeypatch.setattr(
        main_module,
        "_eligible_offers",
        lambda loaded, cfg: [(offers[0], "https://shop.example/1"), (offers[1], "https://shop.example/2")],
    )
    db_path = tmp_path / "state.sqlite3"
    monkeypatch.setattr(main_module, "DB_PATH", db_path)
    original_init_db = main_module.init_db

    def init_with_previous_cycle():
        original_init_db()
        with sqlite3.connect(db_path) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS rotation_posts (
                    cycle_no INTEGER NOT NULL,
                    offer_id TEXT NOT NULL,
                    message_id TEXT,
                    posted_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (cycle_no, offer_id)
                )
            """)
            db.execute(
                "INSERT INTO rotation_posts(cycle_no, offer_id, message_id, posted_at) VALUES (1, ?, ?, ?)",
                ("previously-used-good-photo", "old-message", "2026-11-06 00:00:00"),
            )

    monkeypatch.setattr(main_module, "init_db", init_with_previous_cycle)
    calls = []

    def fake_send(token, channel, caption, photo_url=None):
        calls.append(photo_url)
        if "blocked" in photo_url:
            raise PhotoPreparationError("403 Forbidden")
        return "telegram-message-new-cycle"

    monkeypatch.setattr(main_module, "send_telegram", fake_send)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@test-channel")

    main_module.run_once()

    output = capsys.readouterr().out
    assert "SKIP blocked-photo" in output
    assert "START_CYCLE 2 after image failures" in output
    assert "POSTED previously-used-good-photo cycle=2" in output
    assert calls == [offers[0]["image_url"], offers[1]["image_url"]]
    with sqlite3.connect(db_path) as db:
        posted = db.execute(
            "SELECT cycle_no, offer_id, message_id FROM rotation_posts ORDER BY cycle_no, offer_id"
        ).fetchall()
    assert posted == [
        (1, "previously-used-good-photo", "old-message"),
        (2, "previously-used-good-photo", "telegram-message-new-cycle"),
    ]
