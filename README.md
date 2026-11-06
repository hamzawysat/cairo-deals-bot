# Cairo Deals Bot

A private, modular affiliate publishing system. Amazon Egypt is the first enabled provider; additional stores plug in through separate adapters.

## Current operation
- The publishing workflow is triggered through `workflow_dispatch`; it has no GitHub `schedule` trigger.
- The planned external cron-job.org cadence is every five minutes (`2-59/5 * * * *`).
- The publisher enforces the configured 5-minute minimum interval between Telegram posts.
- At most `max_posts_per_run` eligible offers are published per run (currently 1).
- During scheduler validation, `dry_run` is enabled: eligible offers are listed, but Telegram is not called and SQLite rotation/duplicate state is not changed.
- Offers are ranked by data completeness and optional externally supplied `demand_score` / `quality_score`. These scores must be based on a real source; the bot does not invent demand signals.
- Duplicate offer IDs are skipped using SQLite state restored through Actions cache (best-effort).

## Discovery pipeline
- `src/discovery.py` reads explicitly configured public RSS 2.0 or Atom feeds.
- New items are stored in `data/candidates.json` with original source URL, feed name, and timestamps.
- Every candidate starts as `needs_review`; it is **never published automatically** and receives no assumed Amazon affiliate URL or price.
- Discovery is intentionally disabled until a feed with suitable Egypt-relevant products and terms permitting this use is configured in `config/discovery.json`.
- The bot does not crawl Amazon product pages. Amazon price, availability, image, and affiliate data must come from approved Associates tools.

## Safety
- Only enabled stores and offers are considered.
- Telegram publishing can be disabled with `channels.telegram.enabled=false`.
- HTTPS is required for product links.
- Unknown prices are omitted rather than invented.
- Jumia remains disabled until an official, verified affiliate link/source is available.
- Keep all credentials in GitHub Actions secrets; never commit them.

## Tests
A separate CI workflow runs tests on pushes and pull requests without publishing messages:
`pip install -r requirements.txt pytest`
`python -m pytest -q`
