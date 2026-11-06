# Cairo Deals Bot

A private, modular affiliate publishing system. Amazon Egypt is the first enabled provider; additional stores plug in through separate adapters.

## Current operation
- GitHub Actions runs at minute 7 every two hours (UTC); runs can be delayed by GitHub.
- The publisher enforces the 120-minute minimum interval configured in `config/settings.json`.
- At most `max_posts_per_run` eligible offers are published per run (currently 1).
- Eligible offers are ranked by completeness and optional supplied `demand_score` / `quality_score`. Those scores must come from a real, documented source; the bot does not manufacture demand signals.
- Duplicate offer IDs are skipped using the local SQLite state cache (best-effort persistence in GitHub Actions).

## Current discovery limitation
The bot currently reads its offer queue from `data/offers.json`. It does **not** crawl Amazon or autonomously discover current prices, stock, or trending products. Do not scrape Amazon pages or invent prices, discounts, ratings, images, or demand. New discovery sources must be permitted by their providers and must preserve source URLs and timestamps; Amazon product facts and affiliate links must be verified through approved Associates tools. Creators API integration is a later step after account eligibility.

## Safety
- Only enabled stores and offers are considered.
- Telegram publishing can be disabled with `channels.telegram.enabled=false`.
- HTTPS is required for product links.
- Unknown prices are omitted rather than invented.
- Jumia remains disabled until an official, verified affiliate link/source is available.
- Keep all credentials in GitHub Actions secrets; never commit them.

## Tests
`pip install -r requirements.txt pytest`
`python -m pytest -q`
