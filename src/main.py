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
    price = offer.get("price_egp")
    price_line = f"💰 السعر: {price} جنيه\n" if price is not None else ""
    return f"🔥 {offer['title']}\n\n{price_line}🛒 اطلب من هنا:\n{url}\n\n#ad"

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
