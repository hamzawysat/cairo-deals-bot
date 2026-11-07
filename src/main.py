"""One-run affiliate publisher with deterministic offer ranking."""
import json, os, sqlite3, math
from datetime import datetime, timezone
from pathlib import Path
from .providers import build_affiliate_url, ProviderError
from .publisher import send_telegram, PhotoPreparationError

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("BOT_STATE_DB", ROOT / "data" / "state.sqlite3"))


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _interval_wait_seconds(last_posted_at, now, interval_minutes, grace_seconds):
    """Seconds still to wait after applying a small scheduler-jitter grace window."""
    last_dt = datetime.strptime(last_posted_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    elapsed_seconds = max(0, (now - last_dt).total_seconds())
    remaining_seconds = interval_minutes * 60 - elapsed_seconds - grace_seconds
    return max(0, math.ceil(remaining_seconds))


def _is_valid_price(value):
    """Accept only finite positive numeric prices."""
    try:
        number = float(value)
        return math.isfinite(number) and number > 0
    except (TypeError, ValueError, OverflowError):
        return False


def offer_score(offer):
    """Rank only on supplied signals; never infer demand or product facts."""
    score = 0
    if offer.get("description"):
        score += 10
    features = [item for item in (offer.get("features") or []) if str(item).strip()]
    score += min(len(features), 5) * 4
    if _is_valid_price(offer.get("price_egp")):
        score += 8
    if _has_real_discount(offer.get("original_price_egp"), offer.get("price_egp")):
        score += 6
    for field, cap, weight in (("demand_score", 100, 0.2), ("quality_score", 100, 0.1)):
        try:
            score += max(0, min(float(offer.get(field, 0)), cap)) * weight
        except (TypeError, ValueError):
            pass
    return round(score, 2)


def rank_offers(offers):
    """Highest-scoring eligible offer first; stable input order breaks ties."""
    indexed = [(i, offer) for i, offer in enumerate(offers)]
    indexed.sort(key=lambda pair: (-offer_score(pair[1]), pair[0]))
    return [offer for _, offer in indexed]


def _has_real_discount(original_price, price):
    """Return True only when both supplied prices are finite and positive."""
    if not _is_valid_price(original_price) or not _is_valid_price(price):
        return False
    return float(original_price) > float(price)


def _eligible_offers(offers, settings):
    """Return enabled offers with valid required data and usable HTTPS links."""
    eligible = []
    safety = settings.get("safety", {})
    for offer in offers:
        if not offer.get("enabled") or not offer.get("id") or not offer.get("title"):
            continue
        store_cfg = settings.get("stores", {}).get(offer.get("store"), {})
        if not store_cfg.get("enabled"):
            continue
        if safety.get("skip_missing_price") and not _is_valid_price(offer.get("price_egp")):
            continue
        if safety.get("require_image", True):
            image_url = str(offer.get("image_url") or "").strip()
            if not image_url.startswith("https://"):
                print(f"SKIP {offer['id']}: missing or invalid HTTPS image_url")
                continue
        try:
            url = build_affiliate_url(offer, store_cfg)
        except ProviderError as exc:
            print(f"SKIP {offer.get('id')}: {exc}")
            continue
        if not url.startswith("https://"):
            print(f"SKIP {offer['id']}: product URL must use HTTPS")
            continue
        eligible.append((offer, url))
    return sorted(eligible, key=lambda pair: -offer_score(pair[0]))


def message_for(offer, url):
    """Build a useful, factual Telegram ad without inventing product claims."""
    title = str(offer.get("title") or "منتج مميز").strip()
    description = str(offer.get("description") or "").strip()
    features = offer.get("features") or []
    features = [str(item).strip() for item in features if str(item).strip()]
    price = offer.get("price_egp")
    original_price = offer.get("original_price_egp")
    if not _is_valid_price(price):
        price = None
    lines = [f"✨ {title}", ""]
    if description:
        lines.extend([description, ""])
    if features:
        lines.append("⭐ أبرز الاستخدامات والمميزات:")
        lines.extend(f"• {item}" for item in features)
        lines.append("")
    if price is not None:
        lines.append(f"💰 السعر: {price} جنيه")
    if _has_real_discount(original_price, price):
        lines.append(f"🏷️ السعر السابق: {original_price} جنيه")
    if price is not None or original_price is not None:
        lines.append("")
    lines.extend(["🛍️ شوف التفاصيل واطلب من هنا:", url, ""])
    hashtags = offer.get("hashtags") or ["عروض_القاهرة", "تسوق_أونلاين"]
    clean_tags = []
    for tag in hashtags:
        tag = str(tag).strip().lstrip("#").replace(" ", "_")
        if tag and tag not in clean_tags:
            clean_tags.append(tag)
    lines.append("#إعلان " + " ".join(f"#{tag}" for tag in clean_tags[:5]))
    return "\n".join(lines)


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as db:
        db.execute("CREATE TABLE IF NOT EXISTS posted (offer_id TEXT PRIMARY KEY, message_id TEXT, posted_at TEXT DEFAULT CURRENT_TIMESTAMP)")


def run_once():
    settings = load_json(ROOT / "config" / "settings.json")
    offers_path = ROOT / "data" / "offers.json"
    offers = load_json(offers_path if offers_path.exists() else ROOT / "data" / "offers.example.json")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    channel = os.getenv("TELEGRAM_CHANNEL_ID", "")
    channels = settings.get("channels", {})
    telegram_cfg = channels.get("telegram", {})
    if not telegram_cfg.get("enabled", True):
        print("SKIP: Telegram channel is disabled")
        return

    eligible = _eligible_offers(offers, settings)
    if not eligible:
        print("NO_ELIGIBLE_OFFERS")
        return

    if settings.get("dry_run", False):
        candidate_ids = ",".join(offer.get("id", "unknown") for offer, _ in eligible)
        print(
            f"DRY_RUN: eligible_offers={len(eligible)} candidates={candidate_ids} "
            "telegram_send=SKIPPED database=UNCHANGED rotation=UNCHANGED"
        )
        return

    init_db()
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS rotation_posts (
                cycle_no INTEGER NOT NULL,
                offer_id TEXT NOT NULL,
                message_id TEXT,
                posted_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (cycle_no, offer_id)
            )
        """)
        db.execute("""
            INSERT OR IGNORE INTO rotation_posts(cycle_no, offer_id, message_id, posted_at)
            SELECT 1, offer_id, message_id, posted_at FROM posted
        """)
        interval = max(5, int(settings.get("interval_minutes", 120)))
        grace_seconds = max(0, int(settings.get("interval_grace_seconds", 60)))
        last = db.execute("SELECT MAX(posted_at) FROM rotation_posts").fetchone()[0]
        if last:
            wait_seconds = _interval_wait_seconds(
                last, datetime.now(timezone.utc), interval, grace_seconds
            )
            if wait_seconds > 0:
                print(f"WAIT: {wait_seconds} seconds remain before next post (including {grace_seconds}s scheduler grace)")
                return

        current_cycle = db.execute("SELECT COALESCE(MAX(cycle_no), 1) FROM rotation_posts").fetchone()[0]
        eligible_ids = [offer["id"] for offer, _ in eligible]
        placeholders = ",".join("?" for _ in eligible_ids)
        used = {
            row[0] for row in db.execute(
                f"SELECT offer_id FROM rotation_posts WHERE cycle_no=? AND offer_id IN ({placeholders})",
                [current_cycle, *eligible_ids],
            )
        }
        remaining = [(offer, url) for offer, url in eligible if offer["id"] not in used]
        if not remaining:
            current_cycle += 1
            print(f"START_CYCLE {current_cycle}")
            remaining = eligible

        max_posts = max(1, int(settings.get("max_posts_per_run", 1)))
        posted_count = 0
        for offer, url in remaining:
            if posted_count >= max_posts:
                break
            try:
                message_id = send_telegram(
                    token, channel, message_for(offer, url),
                    photo_url=offer.get("image_url") or None,
                )
            except PhotoPreparationError as exc:
                print(f"SKIP {offer['id']}: image preparation failed; trying next offer: {exc}")
                continue
            db.execute(
                "INSERT INTO rotation_posts(cycle_no, offer_id, message_id) VALUES (?, ?, ?)",
                (current_cycle, offer["id"], message_id),
            )
            db.execute(
                "INSERT OR IGNORE INTO posted(offer_id, message_id) VALUES (?, ?)",
                (offer["id"], message_id),
            )
            db.commit()
            posted_count += 1
            print(f"POSTED {offer['id']} cycle={current_cycle} message_id={message_id} score={offer_score(offer)}")
    if not posted_count:
        print("NO_ELIGIBLE_OFFERS")


if __name__ == "__main__":
    run_once()
