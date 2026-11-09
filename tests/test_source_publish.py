from src.source_publish import (
    mark_candidate_published,
    mark_platform_published,
    select_unpublished_candidate,
    validate_approved_image_record,
)


def test_image_requires_explicit_reuse_permission_and_source():
    assert validate_approved_image_record({
        "url": "https://m.media-amazon.com/images/I/example.jpg",
        "rights_confirmed": True,
        "rights_source": "Merchant written permission",
    }) == "https://m.media-amazon.com/images/I/example.jpg"
    assert validate_approved_image_record({
        "url": "https://m.media-amazon.com/images/I/example.jpg",
        "rights_confirmed": False,
        "rights_source": "Merchant written permission",
    }) is None
    assert validate_approved_image_record({
        "url": "https://m.media-amazon.com/images/I/example.jpg",
        "rights_confirmed": True,
        "rights_source": "",
    }) is None


def test_image_rejects_unapproved_hosts_and_non_https():
    assert validate_approved_image_record({
        "url": "https://evil.example/image.jpg",
        "rights_confirmed": True,
        "rights_source": "Written license from owner",
    }) is None
    assert validate_approved_image_record({
        "url": "http://m.media-amazon.com/image.jpg",
        "rights_confirmed": True,
        "rights_source": "Written license from owner",
    }) is None


def test_exact_message_is_skipped_but_next_message_is_selected():
    candidate = {
        "source_message_id": 22,
        "asin": "B0ABC12345",
        "affiliate_url": "https://www.amazon.eg/dp/B0ABC12345?tag=cairodeals-21",
        "caption_preview": "عرض تجريبي",
        "publishing_performed": False,
    }
    report = {"candidates": [candidate, dict(candidate, source_message_id=23, asin="C0ABC12345")]}
    selected = select_unpublished_candidate(report, {"published_message_ids": [22], "published_asins": ["B0ABC12345"]})
    assert selected["source_message_id"] == 23


def test_published_candidate_is_not_selected_again():
    candidate = {
        "source_message_id": 22,
        "asin": "B0ABC12345",
        "affiliate_url": "https://www.amazon.eg/dp/B0ABC12345?tag=cairodeals-21",
        "caption_preview": "عرض تجريبي",
        "publishing_performed": False,
    }
    assert select_unpublished_candidate(
        {"candidates": [candidate]},
        {"published_message_ids": [22], "published_asins": ["B0ABC12345"]},
    ) is None


def test_publish_state_marks_only_the_exact_message():
    candidate = {"source_message_id": 22, "asin": "B0ABC12345"}
    updated = mark_candidate_published({}, candidate)
    assert updated["published_message_ids"] == [22]


def test_source_publisher_scripts_are_valid_python():
    import ast
    from pathlib import Path

    for filename in (
        "scripts/build_source_offer_previews.py",
        "scripts/publish_one_source_offer.py",
        "scripts/publish_pending_source_offers.py",
        "scripts/inspect_source_samples.py",
    ):
        ast.parse(Path(filename).read_text(encoding="utf-8"), filename=filename)



def test_platform_delivery_state_allows_safe_partial_retry():
    candidate = {"source_message_id": 22, "asin": "B0ABC12345"}
    state = mark_platform_published({}, candidate, "facebook", "meta-post-123")
    status = state["platform_status"]["22"]
    assert status["facebook"] == "meta-post-123"
    assert "telegram" not in status
    assert state.get("published_message_ids", []) == []

    state = mark_platform_published(state, candidate, "telegram", "telegram-456")
    status = state["platform_status"]["22"]
    assert status["facebook"] == "meta-post-123"
    assert status["telegram"] == "telegram-456"
    assert state["published_message_ids"] == [22]


def test_same_product_from_new_source_message_is_allowed():
    candidate = {
        "source_message_id": 23,
        "asin": "B0ABC12345",
        "affiliate_url": "https://www.amazon.eg/dp/B0ABC12345?tag=cairodeals-21",
        "caption_preview": "عرض جديد",
        "publishing_performed": False,
    }
    selected = select_unpublished_candidate(
        {"candidates": [candidate]},
        {"published_message_ids": [22], "published_asins": ["B0ABC12345"]},
    )
    assert selected["source_message_id"] == 23


def test_preview_state_preserves_partial_delivery_records():
    from pathlib import Path
    content = Path("scripts/build_source_offer_previews.py").read_text(encoding="utf-8")
    assert '"platform_status": prior_state.get("platform_status", {})' in content
    assert 'candidate["asin"] in prior_asins' not in content



def test_automatic_publisher_is_gated_and_uses_persisted_pending_queue():
    from pathlib import Path

    content = Path("scripts/publish_pending_source_offers.py").read_text(encoding="utf-8")
    assert 'SOURCE_AUTO_PUBLISH_ENABLED' in content
    assert 'pending_candidates' in content
    assert 'dry_run' in content
    assert 'require_image' in content
    assert 'mark_platform_published' in content


def test_deferred_candidates_move_to_second_position():
    from src.source_publish import defer_candidates_for_retry

    first = {"source_message_id": 1}
    failed = {"source_message_id": 2}
    third = {"source_message_id": 3}
    assert defer_candidates_for_retry([first, failed, third], [failed]) == [first, failed, third]


def test_failed_first_candidate_moves_behind_next_candidate():
    from src.source_publish import defer_candidates_for_retry

    failed = {"source_message_id": 1}
    next_offer = {"source_message_id": 2}
    third = {"source_message_id": 3}
    assert defer_candidates_for_retry([failed, next_offer, third], [failed]) == [next_offer, failed, third]


def test_multiple_failed_candidates_remain_queued_in_stable_order():
    from src.source_publish import defer_candidates_for_retry

    failed_one = {"source_message_id": 1}
    failed_two = {"source_message_id": 2}
    next_offer = {"source_message_id": 3}
    assert defer_candidates_for_retry(
        [failed_one, failed_two, next_offer], [failed_one, failed_two]
    ) == [next_offer, failed_one, failed_two]


def test_retry_queue_does_not_duplicate_deferred_candidate():
    from src.source_publish import defer_candidates_for_retry

    failed = {"source_message_id": 1}
    next_offer = {"source_message_id": 2}
    assert defer_candidates_for_retry([failed, next_offer], [failed, failed]) == [next_offer, failed]



def test_automatic_publisher_verifies_saved_telegram_message_and_passes_product_image():
    from pathlib import Path
    content = Path("scripts/publish_pending_source_offers.py").read_text(encoding="utf-8")
    assert 'client.get_messages(target, ids=int(telegram_id))' in content
    assert 'TELEGRAM STALE STATUS CLEARED' in content
    assert 'publish_facebook, meta_token, caption, str(candidate["_live_image_url"])' in content


def test_manual_publisher_uses_live_image_and_checks_saved_telegram_message():
    from pathlib import Path
    content = Path("scripts/publish_one_source_offer.py").read_text(encoding="utf-8")
    assert 'find_amazon_product_details' in content
    assert 'publish_facebook, meta_token, caption, image_url' in content
    assert 'client.get_messages(target, ids=int(saved_telegram_id))' in content
    assert 'create_telegram_product_card' in content
    assert "قد يتغير السعر أو التوافر لدى المعلن" in content


def test_manual_workflow_does_not_run_automatic_queue_first():
    from pathlib import Path
    content = Path(".github/workflows/check-source-telegram.yml").read_text(encoding="utf-8")
    assert "inputs.publish_one != true" in content



def test_saved_telegram_message_must_match_offer_name_and_affiliate_url():
    from types import SimpleNamespace
    from scripts.publish_pending_source_offers import _telegram_message_matches

    candidate = {
        "product_name_source": "لمبة LED حمراء",
        "affiliate_url": "https://link.amazon/B049WGppS",
    }
    matching = SimpleNamespace(message="🛍️ لمبة LED حمراء\n🔗 https://link.amazon/B049WGppS")
    wrong_offer = SimpleNamespace(message="🛍️ منتج آخر\n🔗 https://link.amazon/OTHER")
    partial_match = SimpleNamespace(message="🛍️ لمبة LED حمراء\n🔗 https://link.amazon/OTHER")

    assert _telegram_message_matches(matching, candidate) is True
    assert _telegram_message_matches(wrong_offer, candidate) is False
    assert _telegram_message_matches(partial_match, candidate) is False


def test_facebook_cadence_is_one_hour_and_waiting_offer_is_not_removed():
    from pathlib import Path
    content = Path("scripts/publish_pending_source_offers.py").read_text(encoding="utf-8")

    assert "FACEBOOK_INTERVAL_SECONDS = 60 * 60" in content
    assert "one-hour interval has not elapsed; offer remains queued for Facebook" in content
    assert "less than 2 hours since last Facebook post" not in content



def test_live_amazon_price_is_mandatory_and_source_price_is_never_used():
    from pathlib import Path
    automatic = Path("scripts/publish_pending_source_offers.py").read_text(encoding="utf-8")
    manual = Path("scripts/publish_one_source_offer.py").read_text(encoding="utf-8")

    assert 'or not _live.get("price")' in automatic
    assert 'candidate["advertised_price"] = str(_live["price"]).strip()' in automatic
    assert 'or not live.get("price")' in manual
    assert 'product_price = str(live["price"]).strip()' in manual
    assert 'live.get("price") or candidate.get("advertised_price")' not in manual


def test_facebook_cadence_is_one_hour_in_automatic_and_manual_publishers():
    from pathlib import Path
    automatic = Path("scripts/publish_pending_source_offers.py").read_text(encoding="utf-8")
    manual = Path("scripts/publish_one_source_offer.py").read_text(encoding="utf-8")

    assert "FACEBOOK_INTERVAL_SECONDS = 10 * 60" in automatic
    assert "one-hour interval has not elapsed; offer remains queued for Facebook" in automatic
    assert "time.time() - last_facebook < 60 * 60" in manual
