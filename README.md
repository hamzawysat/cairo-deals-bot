# Cairo Deals Bot

A private, modular affiliate publishing system. Amazon Egypt is the first enabled provider; Jumia and future stores plug in through separate adapters.

## Architecture
- **Store adapters:** each store builds or validates its own affiliate URL. No store-page scraping.
- **Offer engine:** reads verified offers from `data/offers.json`, skips disabled stores/offers, and avoids reposting the same offer ID.
- **Channel publisher:** Telegram is the first publisher. More channels can be added independently.
- **Schedule:** GitHub Actions checks hourly. `config/settings.json` controls the minimum interval between posts (60, 120, 180 minutes, etc.). The workflow cadence is hourly, so it cannot publish more frequently than that.
- **Safety:** Telegram's JSON response must say `ok: true`; unknown prices are omitted rather than invented.

## First setup
1. Copy `data/offers.example.json` to `data/offers.json` and enter verified products. Keep `enabled: false` until each product and link has been checked.
2. In GitHub: Settings → Secrets and variables → Actions, add:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHANNEL_ID` (for example, `@cairo_deals`)
3. Confirm the bot is an administrator in the target channel.
4. Review `config/settings.json`; keep Jumia disabled until you have a valid Jumia affiliate URL/source.
5. Run Actions → Publish affiliate offer → Run workflow manually.

## Important limitations
- GitHub Actions is a scheduled job runner, not a permanent 24/7 server. Cron runs can be delayed.
- Duplicate-state persistence uses Actions cache and is best-effort, not a transactional database.
- Amazon product prices, stock, and images are not fetched automatically in this first milestone. Only publish details you verify and are permitted to use.
- Jumia affiliate URLs must be supplied from its official affiliate tooling; this project will not guess tracking links or scrape product pages.
- No tokens, passwords, or personal account details belong in the repository.

## Local checks
`pip install -r requirements.txt`
`python -m src.main`
