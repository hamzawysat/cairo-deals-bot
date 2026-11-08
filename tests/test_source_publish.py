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
        "scripts/inspect_source_samples.py",
    ):
        ast.parse(Path(filename).read_text(encoding="utf-8"), filename=filename)



def test_platform_delivery_state_allows_safe_partial_retry():
    candidate = {"source_message_id": 22, "asin": "B0ABC12345"}
    state = mark_platform_published({}, candidate, "facebook", "buffer-123")
    status = state["platform_status"]["22"]
    assert status["facebook"] == "buffer-123"
    assert "telegram" not in status
    assert state.get("published_message_ids", []) == []

    state = mark_platform_published(state, candidate, "telegram", "telegram-456")
    status = state["platform_status"]["22"]
    assert status["facebook"] == "buffer-123"
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
