# Discovery source audit

Last reviewed: 2026-11-06

## Decision

Automatic commercial deal discovery remains disabled. No source is enabled until both its Egypt relevance and its terms for commercial reuse of feed content are verified.

## Sources reviewed

- Jumia Egypt affiliate program: confirms a pay-per-sale affiliate program and describes affiliate links, but the public program page does not document an open RSS/product feed or a public product-data API. Do not treat it as a machine-readable catalog source.
- Jumia JForce: a separate affiliate marketing portal; public landing page does not establish an open product feed for this bot.
- Youm7 technology RSS: a public technology-news feed, not a retail catalog or verified price/deal feed. Do not ingest as product offers.
- Dubizzle RSS terms: RSS use is limited to personal, non-commercial purposes unless a separate license is obtained. Excluded from this commercial affiliate workflow.
- MCIT RSS: free public feeds with attribution terms, but it is government news/information, not product offers or prices. Excluded from product discovery.
- MEED Egypt RSS: country news feed subject to its website terms; not a consumer product catalog. Excluded from product discovery.

## Operating rule

Until an approved source is documented, keep `config/discovery.json` disabled and `sources` empty. RSS candidates must remain review-only; never infer an Amazon/Jumia price, image, availability, or affiliate URL from a news item or an unrelated retailer link.

## Next viable integration

Use Amazon Creators API after the Associates account meets the documented eligibility threshold (10 qualifying sales in the preceding 30 days) and credentials are issued. For Jumia, use only a product feed/API explicitly provided to the approved affiliate account, if available; do not scrape storefront pages or reverse-engineer private endpoints.
