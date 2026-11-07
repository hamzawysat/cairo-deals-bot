# Source monitor (experimental)

The source-monitor code is now maintained on `main` alongside the existing
Cairo Deals bot. The workflow is a manual/read-only verification step; it does
not replace, disable, or publish through the existing scheduled publisher.

## Current safety boundary

- The GitHub Actions check authenticates the Telegram user session, resolves
  `@offersegyptofficial` and `@cairo_deals`, and reads at most ten recent source messages.
- It downloads and validates up to three source photos for read-only OCR.
- The check never sends, edits, forwards, or deletes Telegram messages.
- Telegram credentials are read only from GitHub Actions secrets and are never printed.
- Parsing accepts ASINs only from recognized Amazon hostnames and product paths.
- OCR text alone is not accepted as verified product identity, price, or ASIN.
- Original Arabic caption generation requires independently verified product facts
  and a canonical Amazon Egypt URL carrying the configured tracking tag.
- SQLite state is local to the runner unless a persistent storage service is added.

## Manual connection check

Run **Actions → Check source Telegram access → Run workflow** on the
`main` branch. A successful run confirms account authorization and access to
both channels. It does not publish anything.

## Important deployment limitation

GitHub Actions jobs are short-lived. They are suitable for periodic inspection,
not for a continuously connected Telegram listener. A live listener needs a
separate long-running host and persistent storage. The current source monitor
is not wired into an automatic source-to-publish loop. Do not enable live
publishing until product matching, image rights, retry handling, persistent
deduplication, and both destination paths have been tested and explicitly approved.
