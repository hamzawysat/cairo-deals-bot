from src.main import message_for, offer_score, rank_offers, _target_eligible_offers
from src.providers import build_affiliate_url, ProviderError
from src import main as main_module


def test_amazon_link_contains_tracking_id():
    url = build_affiliate_url({"store":"amazon_eg","title":"دفاية","search_terms":"دفاية"}, {"tracking_id":"cairodeals-21"})
    assert "cairodeals-21" in url
    assert url.startswith("https://www.amazon.eg/")


def test_jumia_needs_verified_affiliate_url():
    try:
        build_affiliate_url({"store":"jumia_eg","title":"منتج"}, {})
        assert False, "Expected ProviderError"
    except ProviderError:
        pass


def test_message_does_not_invent_price():
    text = message_for({"title":"منتج","price_egp":None}, "https://example.com")
    assert "السعر" not in text
    assert "https://example.com" in text


def test_message_includes_description_features_and_hashtags():
    text = message_for({
        "title": "سلك توصيل",
        "description": "للتوصيل في التجارب الإلكترونية.",
        "features": ["توصيل Female إلى Male", "للمشروعات الإلكترونية"],
        "hashtags": ["إلكترونيات", "#مشروعات"],
        "price_egp": None,
    }, "https://example.com/item")
    assert "للتوصيل في التجارب الإلكترونية." in text
    assert "• توصيل Female إلى Male" in text
    assert "#إلكترونيات" in text
    assert "https://example.com/item" in text


def test_message_shows_price_only_when_provided():
    text = message_for({
        "title": "منتج",
        "price_egp": 120,
        "original_price_egp": 150,
    }, "https://example.com")
    assert "💰 السعر: 120 جنيه" in text
    assert "🏷️ السعر السابق: 150 جنيه" in text


def test_offer_score_rewards_complete_verified_data():
    basic = {"title": "منتج"}
    complete = {
        "title": "منتج", "description": "وصف موثق",
        "features": ["ميزة 1", "ميزة 2"], "price_egp": 100,
        "original_price_egp": 130, "demand_score": 80, "quality_score": 90,
    }
    assert offer_score(complete) > offer_score(basic)


def test_rank_offers_is_highest_score_first_and_stable_for_ties():
    low = {"id": "low", "title": "منتج"}
    high = {"id": "high", "title": "منتج", "description": "وصف", "features": ["ميزة"]}
    equal_a = {"id": "a", "title": "A"}
    equal_b = {"id": "b", "title": "B"}
    ranked = rank_offers([low, high, equal_a, equal_b])
    assert [item["id"] for item in ranked] == ["high", "low", "a", "b"]


def test_dry_run_does_not_send_or_touch_database(tmp_path, monkeypatch, capsys):
    settings = {"dry_run": True, "channels": {"telegram": {"enabled": True}}}
    offers = [{"id": "demo-1", "title": "Demo"}]

    def fake_load_json(path):
        return settings if str(path).endswith("settings.json") else offers

    monkeypatch.setattr(main_module, "load_json", fake_load_json)
    monkeypatch.setattr(
        main_module,
        "_eligible_offers",
        lambda loaded_offers, loaded_settings: [(loaded_offers[0], "https://example.com/item")],
    )
    database_path = tmp_path / "state.sqlite3"
    monkeypatch.setattr(main_module, "DB_PATH", database_path)

    def forbidden_send(*args, **kwargs):
        raise AssertionError("Telegram must not be called during dry_run")

    monkeypatch.setattr(main_module, "send_telegram", forbidden_send)
    main_module.run_once()

    output = capsys.readouterr().out
    assert "DRY_RUN" in output
    assert "telegram_send=SKIPPED" in output
    assert "database=UNCHANGED" in output
    assert "rotation=UNCHANGED" in output
    assert not database_path.exists()



def test_targeted_manual_publish_selects_only_exact_offer():
    jam = ({"id": "amazon-miro-strawberry-fig-jam-016"}, "https://example.com/jam")
    other = ({"id": "other-offer"}, "https://example.com/other")
    assert _target_eligible_offers([other, jam], "amazon-miro-strawberry-fig-jam-016") == [jam]


def test_targeted_manual_publish_does_not_fall_back_to_another_offer():
    other = ({"id": "other-offer"}, "https://example.com/other")
    assert _target_eligible_offers([other], "amazon-miro-strawberry-fig-jam-016") == []


def test_normal_publish_keeps_all_eligible_offers():
    first = ({"id": "first"}, "https://example.com/1")
    second = ({"id": "second"}, "https://example.com/2")
    assert _target_eligible_offers([first, second], "") == [first, second]
