from src.source_offer import (
    build_source_candidate,
    extract_product_name,
    extract_source_price,
    extract_urls,
    is_allowed_amazon_url,
    resolve_amazon_product_url,
)


def test_only_https_amazon_hosts_are_allowed():
    assert is_allowed_amazon_url("https://amzn.to/abc")
    assert is_allowed_amazon_url("https://www.amazon.eg/dp/B0ABC12345")
    assert is_allowed_amazon_url("https://www.amazon.sa/dp/B0ABC12345")
    assert is_allowed_amazon_url("https://amzlinks.in/short")
    assert not is_allowed_amazon_url("https://subdomain.amzlinks.in/short")
    assert not is_allowed_amazon_url("http://www.amazon.eg/dp/B0ABC12345")
    assert not is_allowed_amazon_url("https://evil.example/dp/B0ABC12345")
    assert not is_allowed_amazon_url("https://amazon.eg.evil.example/dp/B0ABC12345")
    assert not is_allowed_amazon_url("https://user:pass@amazon.eg/dp/B0ABC12345")
    assert not is_allowed_amazon_url("https://amazon.eg:8443/dp/B0ABC12345")


def test_extract_urls_includes_hidden_entities_and_deduplicates():
    assert extract_urls(
        "عرض https://amzn.to/abc",
        ["https://amzn.to/abc", "https://www.amazon.eg/dp/B0ABC12345"],
    ) == ["https://amzn.to/abc", "https://www.amazon.eg/dp/B0ABC12345"]


def test_redirect_resolution_rejects_off_domain_redirect():
    class Response:
        status_code = 302
        headers = {"Location": "https://evil.example/steal"}
        def close(self):
            pass
    class Session:
        trust_env = True
        def get(self, *args, **kwargs):
            return Response()
    assert resolve_amazon_product_url("https://amzn.to/abc", session=Session()) is None


def test_redirect_resolution_accepts_amazon_product_redirect():
    class Response:
        status_code = 302
        headers = {"Location": "https://www.amazon.eg/dp/B0ABC12345"}
        def close(self):
            pass
    class FinalResponse:
        status_code = 200
        headers = {}
        def close(self):
            pass
    class Session:
        trust_env = True
        calls = 0
        def get(self, *args, **kwargs):
            self.calls += 1
            return Response() if self.calls == 1 else FinalResponse()
    result = resolve_amazon_product_url("https://amzn.to/abc", session=Session())
    assert result == ("B0ABC12345", "https://www.amazon.eg/dp/B0ABC12345")


def test_product_name_comes_from_source_text_not_price_or_cta():
    assert extract_product_name(
        "لمبة LED حمراء 5 ملم - 5 قطع\nالسعر 10.80 جنيه\nاطلب الآن"
    ) == "لمبة LED حمراء 5 ملم - 5 قطع"


def test_candidate_requires_one_resolved_asin_and_explicit_egp_price():
    resolver = lambda url: ("B0ABC12345", "https://www.amazon.eg/dp/B0ABC12345")
    result = build_source_candidate(
        message_id=77,
        message_text="لمبة LED حمراء 5 ملم - 5 قطع\nالسعر 10.80 جنيه\nhttps://amzn.to/item",
        resolver=resolver,
    )
    assert result is not None
    assert result["asin"] == "B0ABC12345"
    assert result["advertised_price"] == "10.80 جنيه"
    assert result["affiliate_url"] == "https://www.amazon.eg/dp/B0ABC12345?tag=cairodeals-21"
    assert result["publishing_performed"] is False
    assert "review_only" in result["image_status"]


def test_candidate_rejects_missing_price_or_ambiguous_asins():
    resolver = lambda url: ("B0ABC12345", "https://www.amazon.eg/dp/B0ABC12345")
    assert build_source_candidate(
        message_id=1,
        message_text="لمبة LED حمراء\nhttps://amzn.to/item",
        resolver=resolver,
    ) is None
    ambiguous = lambda url: ("B0ABC12345" if "one" in url else "C0ABC12345", "x")
    assert build_source_candidate(
        message_id=2,
        message_text="لمبة LED حمراء\nالسعر 10 جنيه\nhttps://amzn.to/one https://amzn.to/two",
        resolver=ambiguous,
    ) is None



def test_sar_source_price_preserves_current_price_and_currency():
    assert extract_source_price(
        "السعر السابق 21 ريال\nالسعر الحالي 11 ريال"
    ) == ("11 ريال سعودي", "SAR")


def test_candidate_accepts_amazon_sa_redirect_and_flags_sar_for_review():
    responses = []
    class RedirectResponse:
        status_code = 302
        headers = {"Location": "https://www.amazon.sa/dp/B0ABC12345"}
        def close(self):
            pass
    class FinalResponse:
        status_code = 200
        headers = {}
        def close(self):
            pass
    class Session:
        trust_env = True
        calls = 0
        def get(self, *args, **kwargs):
            self.calls += 1
            return RedirectResponse() if self.calls == 1 else FinalResponse()

    from src.source_offer import resolve_amazon_product_url
    resolved = resolve_amazon_product_url(
        "https://link.amazon/B0short12", session=Session()
    )
    assert resolved == ("B0ABC12345", "https://www.amazon.eg/dp/B0ABC12345")

    candidate = build_source_candidate(
        message_id=90,
        message_text=(
            "منظف مرحاض جيف مضاد للبكتيريا 750 مل\n"
            "السعر السابق 21 ريال\n"
            "السعر الحالي 11 ريال\n"
            "https://link.amazon/B0short12"
        ),
        resolver=lambda url: resolved,
    )
    assert candidate is not None
    assert candidate["currency"] == "SAR"
    assert candidate["advertised_price"] == "11 ريال سعودي"
    assert "لم يتم تحويله للجنيه المصري" in candidate["caption_preview"]
    assert candidate["review_status"].startswith("preview_ready_but_sar")



def test_shortlink_intermediary_must_end_at_an_amazon_product():
    class FirstRedirect:
        status_code = 302
        headers = {"Location": "https://amzlinks.in/resolve/abc"}
        def close(self):
            pass
    class SecondRedirect:
        status_code = 302
        headers = {"Location": "https://www.amazon.sa/dp/B0ABC12345"}
        def close(self):
            pass
    class FinalResponse:
        status_code = 200
        headers = {}
        def close(self):
            pass
    class Session:
        trust_env = True
        calls = 0
        def get(self, *args, **kwargs):
            self.calls += 1
            return [FirstRedirect(), SecondRedirect(), FinalResponse()][self.calls - 1]

    result = resolve_amazon_product_url(
        "https://link.amazon/B0short12", session=Session()
    )
    assert result == ("B0ABC12345", "https://www.amazon.eg/dp/B0ABC12345")
