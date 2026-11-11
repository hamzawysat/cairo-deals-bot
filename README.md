# Hamzawy Deals

A modular affiliate publishing system serving Hamzawy Sat. Amazon Egypt is the first enabled provider; additional stores plug in through separate adapters.

## Runtime model
- Production publishing is intended to run locally from Termux. GitHub Actions and external cron-job.org are not part of the production runtime.
- Do not dispatch `.github/workflows/check-source-telegram.yml`: its default path can publish queued offers.
- The configured `interval_minutes` is currently 2 minutes for testing; the planned normal cadence is 120 minutes when the local schedule is finalized.
- `interval_grace_seconds` is currently 60 seconds and absorbs small scheduler/network timing differences.
- At most `max_posts_per_run` eligible offers are published per run (currently 1).
- `dry_run` is currently false, so a local run can publish to enabled channels.
- Facebook publishing has a separate one-hour cadence; Telegram cadence remains independently controlled.
- Offers must have an HTTPS product URL. Image requirements are controlled by `safety.require_image`.
- Offers are ranked by data completeness and optional externally supplied `demand_score` / `quality_score`. These scores must be based on a real source; the bot does not invent demand signals.
- Duplicate offer IDs are protected by local SQLite state; source-channel delivery state is persisted separately under `artifacts/`.

## Visual identity
- Telegram product cards use the Hamzawy Sat black, gold, and cream palette.
- The official Hamzawy Sat logo is stored at `assets/brand/hamzawy-sat-logo.png` and embedded in generated cards.
- Product image, name, and supplied price remain the primary offer content; no invented discount or price is added.

## Discovery pipeline
- `src/discovery.py` reads explicitly configured public RSS 2.0 or Atom feeds.
- New items are stored in `data/candidates.json` with original source URL, feed name, and timestamps.
- Every candidate starts as `needs_review`; it is **never published automatically** and receives no assumed Amazon affiliate URL or price.
- Discovery is intentionally disabled until a feed with suitable Egypt-relevant products and terms permitting this use is configured in `config/discovery.json`.
- The bot does not crawl Amazon product pages. Amazon price, availability, image, and affiliate data must come from approved Associates tools.

## Safety
- Only enabled stores and offers are considered.
- Telegram publishing can be disabled with `channels.telegram.enabled=false`.
- HTTPS is required for product links and (by default) product images.
- Unknown prices are omitted rather than invented.
- Jumia remains disabled until an official, verified affiliate link/source is available.
- Keep credentials in the local Termux environment only; never commit them. GitHub Actions secrets are not used for production operation.

## Tests
A separate CI workflow runs tests on pushes to main and pull requests targeting main:
`pip install -r requirements.txt pytest`
`python -m pytest -q`
