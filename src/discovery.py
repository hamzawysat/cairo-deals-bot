"""Collect public RSS/Atom deal leads into a review queue; never auto-publish them."""
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "discovery.json"
QUEUE = ROOT / "data" / "candidates.json"
HEADERS = {"User-Agent": "CairoDealsBot/1.0 (+RSS feed reader)"}


def _text(element, names):
    for name in names:
        found = element.find(name)
        if found is not None and found.text:
            return found.text.strip()
    return ""


def _date(value):
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError):
            return None


def parse_feed(xml_text, source_name, source_url):
    """Parse RSS 2.0 and Atom. Preserve original link and source attribution."""
    root = ET.fromstring(xml_text)
    items = root.findall(".//item")
    if not items:
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
    results = []
    for item in items:
        title = _text(item, ["title", "{http://www.w3.org/2005/Atom}title"])
        link = _text(item, ["link"])
        if not link:
            atom_link = item.find("{http://www.w3.org/2005/Atom}link")
            if atom_link is not None:
                link = atom_link.attrib.get("href", "").strip()
        description = _text(item, ["description", "summary", "{http://www.w3.org/2005/Atom}summary", "{http://www.w3.org/2005/Atom}content"])
        published = _text(item, ["pubDate", "published", "updated", "{http://www.w3.org/2005/Atom}published", "{http://www.w3.org/2005/Atom}updated"])
        if not title or not link:
            continue
        parsed = urlparse(link)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            continue
        stable = re.sub(r"[^a-zA-Z0-9]+", "-", (source_name + "-" + link).lower()).strip("-")[-180:]
        results.append({
            "id": stable,
            "title": title,
            "source_name": source_name,
            "source_feed": source_url,
            "source_url": link,
            "description": re.sub(r"<[^>]+>", " ", description).strip()[:1200],
            "published_at": _date(published),
            "discovered_at": datetime.now(timezone.utc).isoformat(),
            "status": "needs_review",
            "affiliate_url": None,
            "price_egp": None,
        })
    return results


def discover(sources, output_path=QUEUE, timeout=15):
    """Fetch only explicitly configured public feeds and merge unseen candidates."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else []
    except (OSError, json.JSONDecodeError):
        existing = []
    known = {item.get("id") for item in existing}
    added = []
    for source in sources:
        if not source.get("enabled"):
            continue
        feed_url = str(source.get("url") or "").strip()
        parsed = urlparse(feed_url)
        if parsed.scheme != "https" or not parsed.netloc:
            continue
        try:
            response = requests.get(feed_url, headers=HEADERS, timeout=timeout)
            response.raise_for_status()
            for candidate in parse_feed(response.text, source.get("name") or parsed.netloc, feed_url):
                if candidate["id"] not in known:
                    known.add(candidate["id"])
                    added.append(candidate)
        except (requests.RequestException, ET.ParseError) as exc:
            print(f"DISCOVERY_SOURCE_ERROR {source.get('name', feed_url)}: {exc}")
    merged = existing + added
    output_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"DISCOVERY: {len(added)} new candidates; {len(merged)} awaiting review")
    return added


def run():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if not config.get("enabled"):
        print("DISCOVERY_DISABLED")
        return []
    return discover(config.get("sources", []))


if __name__ == "__main__":
    run()
