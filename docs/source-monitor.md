# Source monitor (experimental)

This is an isolated experiment on the `source-monitor` branch. It does not replace
or modify the existing scheduled publisher on `main`.

## Current safety boundary

- The manual GitHub Actions check authenticates the Telegram user session, resolves
  `@amzon44` and `@cairo_deals`, and reads at most three recent source messages.
- The check never sends, edits, forwards, or deletes messages.
- Telegram credentials are read only from GitHub Actions secrets and are never printed.
- Parsing accepts ASINs only from recognized Amazon hostnames and product paths.
- The formatter preserves supplied source text and does not invent prices or discounts.
- SQLite state is isolated at `data/source_monitor.sqlite3`.

## Manual connection check

Run **Actions → Check source Telegram access → Run workflow** on the
`source-monitor` branch. A successful run confirms account authorization and
access to both channels. It does not publish anything.

## Important deployment limitation

GitHub Actions jobs are short-lived. They are suitable for this manual check,
not for a continuously connected Telegram listener. A live listener needs a
separate long-running host and persistent storage. Do not enable live publishing
until that hosting, image handling, retry policy, and both destination paths
have been tested and explicitly approved.
