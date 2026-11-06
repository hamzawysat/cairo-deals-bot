from src.discovery import parse_feed


def test_parse_rss_candidate_keeps_source_link_and_marks_unverified():
    xml = """<?xml version="1.0"?>
    <rss version="2.0"><channel><item>
      <title>Example electronics deal</title>
      <link>https://merchant.example/item/123</link>
      <description>Public feed summary</description>
      <pubDate>Fri, 06 Nov 2026 08:00:00 +0000</pubDate>
    </item></channel></rss>"""
    items = parse_feed(xml, "Example Feed", "https://feed.example/rss.xml")
    assert len(items) == 1
    assert items[0]["source_url"] == "https://merchant.example/item/123"
    assert items[0]["source_name"] == "Example Feed"
    assert items[0]["price_egp"] is None
    assert items[0]["affiliate_url"] is None
    assert items[0]["status"] == "needs_review"


def test_parse_atom_feed():
    xml = """<feed xmlns="http://www.w3.org/2005/Atom">
      <entry><title>Atom product</title>
      <link href="https://shop.example/p/1"/>
      <summary>Summary</summary><updated>2026-11-06T08:00:00Z</updated>
      </entry></feed>"""
    items = parse_feed(xml, "Atom", "https://feed.example/atom.xml")
    assert len(items) == 1
    assert items[0]["title"] == "Atom product"
    assert items[0]["source_url"] == "https://shop.example/p/1"


def test_reject_invalid_or_missing_links():
    xml = """<rss><channel>
      <item><title>No link</title></item>
      <item><title>Bad link</title><link>javascript:alert(1)</link></item>
    </channel></rss>"""
    assert parse_feed(xml, "Feed", "https://feed.example/rss") == []
