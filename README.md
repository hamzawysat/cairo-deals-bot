# Cairo Deals Bot

A private, modular affiliate publishing system. Amazon Egypt is the first enabled provider; additional stores plug in through separate adapters.

## Current operation
- The publishing workflow is triggered through `workflow_dispatch`; it has no GitHub `schedule` trigger.
- The external cron-job.org schedule is intended to run every five minutes (`2-59/5 * * * *`).
- The publisher enforces the configured minimum interval between successful Telegram posts (currently 5 minutes for testing; set to 120 minutes for the later two-hour cadence).
- A configurable `interval_grace_seconds` (currently 60 seconds) absorbs small cron/network timing differences. It prevents a run arriving a few seconds early from postponing the post until the next five-minute scheduler tick. The grace is subtracted from the interval; it does not remove the interval protection.
- At most `max_posts_per_run` eligible offers are published per run (currently 1).
- `dry_run` is currently false, so eligible offers can be published to Telegram.
- Offers must have an HTTPS product URL and, by default, a non-empty HTTPS `image_url`. Offers without an image are skipped instead of being published as text-only ads. Add a verified image URL before enabling such an offer.
- Offers are ranked by data completeness and optional externally supplied `demand_score` / `quality_score`. These scores must be based on a real source; the bot does not invent demand signals.
- Duplicate offer IDs are skipped using SQLite state restored through Actions cache (best-effort).

## Facebook Page publishing
- A separate publisher is available in `src/facebook_publisher.py`; it uploads the complete product image (no crop) and caption to the configured Facebook Page using Meta Graph API.
- Facebook is disabled by default in `config/settings.json` and is not connected to the scheduled Telegram workflow. Adding this module does not publish anything to Facebook.
- Configure `FACEBOOK_PAGE_ID`, `FACEBOOK_PAGE_ACCESS_TOKEN`, and optionally `FACEBOOK_GRAPH_API_VERSION` as GitHub Actions secrets before a separately reviewed integration step.
- The Page token needs the `pages_manage_posts`, `pages_read_engagement`, and `pages_show_list` permissions as applicable to the Page publishing flow. The person authorizing the token must have a Page task that permits creating content.
- Current default Graph API version: `v26.0`. Confirm the version and token validity before enabling live publishing.

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
- Keep all credentials in GitHub Actions secrets; never commit them.

## Tests
A separate CI workflow runs tests on pushes to main and pull requests targeting main:
`pip install -r requirements.txt pytest`
`python -m pytest -q`
