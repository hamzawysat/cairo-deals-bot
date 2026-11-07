# Source monitor and one-item Telegram publisher

The source workflow reads `@OffersEgyptofficial`, resolves Amazon short links, and builds
Arabic offer previews. It runs on a two-hour schedule and after pushes to
`main`. The normal scheduled and push runs are read-only: they do not post to
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
`publish_one` unchecked for preview-only operation. Checking it opts into one
Telegram post to `@cairo_deals`, but the job still stops unless the report
contains a new candidate and the ASIN has an approved image manifest entry.
The publisher never forwards or republishes the source-channel photo.

The one-item action is separate from the existing scheduled product publisher.
It does not change the existing offer cadence or its Facebook/Buffer flow.

## State and operational limits

GitHub Actions cache is used as best-effort deduplication between scheduled
runs; it is not a transactional database and cannot guarantee exactly-once
delivery after an interrupted network request. A permanent unattended listener
requires a long-running host and durable database. No live post is performed
by the normal workflow.
