"""One-run publisher. Designed for scheduled jobs, not a permanent daemon."""
import json, os, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .providers import build_affiliate_url, ProviderError
from .publisher import send_telegram

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("BOT_STATE_DB", ROOT / "data" / "state.sqlite3"))

def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

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
    if original_price is not None and price is not None and float(original_price) > float(price):
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
    init_db()
    with sqlite3.connect(DB_PATH) as db:
        interval = max(60, int(settings.get("interval_minutes", 60)))
        last = db.execute("SELECT MAX(posted_at) FROM posted").fetchone()[0]
        if last:
            last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds() / 60
            if elapsed < interval:
                print(f"WAIT: {interval - elapsed:.0f} minutes remain before next post")
                return
        for offer in offers:
            if not offer.get("enabled") or not offer.get("id") or not offer.get("title"):
                continue
            store_cfg = settings.get("stores", {}).get(offer.get("store"), {})
            if not store_cfg.get("enabled"):
                continue
            if db.execute("SELECT 1 FROM posted WHERE offer_id=?", (offer["id"],)).fetchone():
                continue
            try:
                url = build_affiliate_url(offer, store_cfg)
            except ProviderError as exc:
                print(f"SKIP {offer.get('id')}: {exc}")
                continue
            if settings.get("safety", {}).get("require_product_url") and not url.startswith("https://"):
                print(f"SKIP {offer['id']}: invalid URL")
                continue
            message_id = send_telegram(token, channel, message_for(offer, url))
            db.execute("INSERT INTO posted(offer_id, message_id) VALUES (?, ?)", (offer["id"], message_id))
            db.commit()
            print(f"POSTED {offer['id']} message_id={message_id}")
            return
    print("NO_ELIGIBLE_OFFERS")

if __name__ == "__main__":
    run_once()
