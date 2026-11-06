"""Store-specific affiliate URL builders. No scraping is performed here."""
from urllib.parse import quote_plus

class ProviderError(ValueError):
    pass

def build_affiliate_url(offer: dict, store_settings: dict) -> str:
    store = offer.get("store")
    supplied = (offer.get("affiliate_url") or "").strip()
    if supplied:
        return supplied
    if store == "amazon_eg":
        tracking_id = (store_settings.get("tracking_id") or "").strip()
        terms = (offer.get("search_terms") or offer.get("title") or "").strip()
        if not tracking_id or not terms:
            raise ProviderError("Amazon offer needs tracking_id and search terms")
        return f"https://www.amazon.eg/s?k={quote_plus(terms)}&tag={quote_plus(tracking_id)}"
    if store == "jumia_eg":
        raise ProviderError("Jumia requires a verified affiliate URL; automatic link generation is not enabled")
    raise ProviderError(f"Unsupported store: {store}")
