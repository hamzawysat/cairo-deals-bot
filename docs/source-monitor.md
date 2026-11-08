# Source monitor and one-item Telegram publisher

The source workflow reads `@OffersEgyptofficial`, resolves Amazon short links, and builds
Arabic offer previews. It polls every ten minutes using a saved Telegram message cursor. The first
run inspects up to 100 recent posts; later runs process only messages newer than
the saved cursor. It can still be delayed by GitHub Actions scheduling. The normal scheduled and push runs are read-only: they do not post to
Telegram or Facebook.

## Link resolution

- Accepts only HTTPS URLs from the explicit Amazon/short-link host allowlist.
- Follows redirects manually (maximum eight) and checks every hop.
- Rejects off-allowlist hosts, private/non-public DNS results, missing redirect
  locations, failed HTTP responses, and destinations without one unambiguous ASIN.
- Rebuilds the Egyptian affiliate URL using `cairodeals-21`; source tags are not reused.
- Requires one ASIN and an explicit EGP price. Ambiguous products and other
  currencies are rejected for review.

## Image reuse

Photos downloaded from `@OffersEgyptofficial` are OCR evidence only. They are not copied
into the preview or republished. The optional publisher reads
`config/approved_product_images.json` and requires, per ASIN:
- an HTTPS image URL on an approved Amazon image CDN;
- `rights_confirmed: true`;
- a non-empty `rights_source` identifying the permission or license.

The manifest is intentionally empty by default. Do not mark an image approved
unless you actually have permission to reuse it.

Example entry (replace with a real, authorized image and permission record):

```json
{
  "products": {
    "B0XXXXXXXX": {
      "url": "https://m.media-amazon.com/images/I/example.jpg",
      "rights_confirmed": true,
      "rights_source": "Written permission from the image owner, dated YYYY-MM-DD"
    }
  }
}
```

## One-item publishing

Use **Actions → Build source offer previews → Run workflow**. Keep
`publish_one` unchecked for preview-only operation. Checking it is an explicit
manual approval to publish exactly one review-ready offer as a text post to
`@cairo_deals` and the configured Facebook page through Buffer.

The publisher requires the Telegram user session, `BUFFER_API_KEY`, and the
Facebook channel ID in `config/settings.json`. It does not copy the source
channel photo. The product link is included in the Arabic caption; Telegram
and Facebook may render their own link previews. This text-only fallback avoids
reusing an image without documented rights.

Each destination confirmation is saved independently. If Facebook succeeds
but Telegram fails (or vice versa), the next manual retry skips the destination
already confirmed and attempts only the unfinished one. A successful full
delivery marks the source message and ASIN as published.

The workflow remains review-only on its schedule. No automatic live publishing
is enabled by these changes.

## State and operational limits

GitHub Actions cache is used as best-effort deduplication between scheduled
runs; it is not a transactional database and cannot guarantee exactly-once
delivery after an interrupted network request. A permanent unattended listener
requires a long-running host and durable database. No live post is performed
by the normal workflow.
