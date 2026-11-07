import sqlite3

from src import main as main_module


def test_run_once_publishes_text_without_uploading_product_photo(
    tmp_path, monkeypatch, capsys
):
    settings = {
        "dry_run": False,
        "interval_minutes": 5,
        "max_posts_per_run": 1,
        "channels": {"telegram": {"enabled": True}},
        "stores": {},
    }
    offers = [
        {
            "id": "offer-with-image-url",
            "title": "منتج بصورة",
            "price_egp": 100,
            "image_url": "https://images.example/product.jpg",
        }
    ]
    monkeypatch.setattr(
        main_module,
        "load_json",
        lambda path: settings if str(path).endswith("settings.json") else offers,
    )
    monkeypatch.setattr(
        main_module,
        "_eligible_offers",
        lambda loaded, cfg: [(offers[0], "https://link.amazon/example")],
    )
    db_path = tmp_path / "state.sqlite3"
    monkeypatch.setattr(main_module, "DB_PATH", db_path)
    calls = []

    def fake_send(token, channel, message):
        calls.append((token, channel, message))
        return "telegram-message-1"

    monkeypatch.setattr(main_module, "send_telegram", fake_send)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@test-channel")

    main_module.run_once()

    output = capsys.readouterr().out
    assert "POSTED offer-with-image-url" in output
    assert len(calls) == 1
    token, channel, message = calls[0]
    assert token == "test-token"
    assert channel == "@test-channel"
    assert message.splitlines() == [
        "🛍️ منتج بصورة",
        "💰 100 جنيه",
        "👇 https://link.amazon/example",
    ]
    with sqlite3.connect(db_path) as db:
        posted = db.execute(
            "SELECT offer_id, message_id FROM rotation_posts"
        ).fetchall()
    assert posted == [("offer-with-image-url", "telegram-message-1")]
