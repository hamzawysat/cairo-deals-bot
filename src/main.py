"""One-run affiliate publisher with deterministic offer ranking."""
import json, os, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .providers import build_affiliate_url, ProviderError
from .publisher import send_telegram

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("BOT_STATE_DB", ROOT / "data" / "state.sqlite3"))


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def offer_score(offer):
    """Rank only on supplied signals; never infer demand or product facts."""
    score = 0
    if offer.get("description"):
        score += 10
    features = [item for item in (offer.get("features") or []) if str(item).strip()]
    score += min(len(features), 5) * 4
    if offer.get("price_egp") is not None:
        score += 8
    if offer.get("original_price_egp") is not None and offer.get("price_egp") is not None:
        try:
            if float(offer["original_price_egp"]) > float(offer["price_egp"]):
                score += 6
        except (TypeError, ValueError):
            pass
    # These are optional, externally verified numeric signals. Missing means zero.
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
    """Return True only when supplied prices are valid and original is higher."""
    try:
        return original_price is not None and price is not None and float(original_price) > float(price)
    except (TypeError, ValueError, OverflowError):
        return False


def message_for(offer, url):
    """Build a useful, factual Telegram ad without inventing product claims."""
    title = str(offer.get("title") or "منتج مميز").strip()
    description = str(offer.get("description") or "").strip()
    features = offer.get("features") or []
    features = [str(item).strip() for item in features if str(item).strip()]
    price = offer.get("price_egp")
    original_price = offer.get("original_price_egp")
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
    init_db()
    with sqlite3.connect(DB_PATH) as db:
        interval = max(60, int(settings.get("interval_minutes", 120)))
        last = db.execute("SELECT MAX(posted_at) FROM posted").fetchone()[0]
        if last:
            last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds() / 60
            if elapsed < interval:
                print(f"WAIT: {interval - elapsed:.0f} minutes remain before next post")
                return
        eligible = []
        for offer in offers:
            if not offer.get("enabled") or not offer.get("id") or not offer.get("title"):
                continue
            store_cfg = settings.get("stores", {}).get(offer.get("store"), {})
            if not store_cfg.get("enabled"):
                continue
            if settings.get("safety", {}).get("skip_missing_price") and offer.get("price_egp") is None:
                continue
            if db.execute("SELECT 1 FROM posted WHERE offer_id=?", (offer["id"],)).fetchone():
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
        eligible.sort(key=lambda pair: -offer_score(pair[0]))
        max_posts = max(1, int(settings.get("max_posts_per_run", 1)))
        posted_count = 0
        for offer, url in eligible[:max_posts]:
            message_id = send_telegram(token, channel, message_for(offer, url))
            db.execute("INSERT INTO posted(offer_id, message_id) VALUES (?, ?)", (offer["id"], message_id))
            db.commit()
            posted_count += 1
            print(f"POSTED {offer['id']} message_id={message_id} score={offer_score(offer)}")
    if not posted_count:
        print("NO_ELIGIBLE_OFFERS")


if __name__ == "__main__":
    run_once()
