# vps-deals

Main site: [vps-deals](https://vps-deals-promo-radar-2hi.pages.dev/)

**Official-source VPS price watch. See the source.**

The static site lists VPS providers and displays a price only when it can be read unambiguously from an official public source. It does not estimate discounts, renewals, or commissions. Provider source URLs, brand, niche, and the published base URL are configured in [.ilang/site.ilang](.ilang/site.ilang). The Python scraper and builder read that file directly.

## Local build

```sh
python scraper.py
python build.py
```

The scraper follows each source domain's `robots.txt`, requests only the configured official page, and accepts only clearly structured official `Offer` data with a plan name, price, and currency. Ambiguous or expired offers are omitted. The static output is generated into `site/`.

GitHub Actions runs every six hours and commits only when generated data or pages change. Cloudflare Pages should use build command `python build.py` and output directory `site`. After Cloudflare assigns the production URL, set `base_url` and `domain` in `.ilang/site.ilang` to that exact URL; this enables correct canonical tags and absolute sitemap URLs.

Affiliate links are intentionally blank until a real approved program URL is supplied. No commissions are asserted. GitHub is the first distribution channel; no social accounts are part of this first version.

Site rules are described using the I-Lang protocol in [.ilang/site.ilang](.ilang/site.ilang); protocol information: [ilang.ai](https://ilang.ai).

Billing period, upfront commitment, eligibility and renewal amounts are not currently extracted. Prices are source snapshots, not independently confirmed discounts. Scheduled runs are best effort and depend on GitHub Actions availability.
