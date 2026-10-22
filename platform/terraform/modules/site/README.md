# site module

I use this module to put the website on CloudFront. The site files live in a private S3 bucket, and CloudFront is the only thing that can read them.

What it does:

- **Private access.** CloudFront signs every request to the bucket. The storage module's bucket policy lets only this distribution read the site bucket.
- **HTTPS only.** Requests on plain http are redirected to https.
- **A fresh status page.** `status.json` is never cached, so the status page always shows the latest run. Everything else uses the managed caching policy.
- **No public data files.** The Lambda function reads the Parquet files in `published/` directly from the bucket. Readers have no use for them, so a small CloudFront function answers 403 for any request under `published/`.
- **Page links work.** S3 answers 403 for a missing file when access is private. A missing path returns `index.html` with a 200, so the app can handle its own page links.
- **The cheapest price class,** `PriceClass_100`, which stays inside CloudFront's free allowance for my traffic.

I use the default `cloudfront.net` address and certificate for now. A custom domain is a later step.

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `env` | string | none | `dev` or `live`. |
| `bucket_regional_domain_name` | string | none | Regional domain of the site bucket, from the storage module. |

## Outputs

| Name | Description |
|---|---|
| `distribution_arn` | Pass to the storage module as `site_distribution_arn`. |
| `domain_name` | Address of the site. |
| `distribution_id` | ID of the distribution. The deploy workflow clears its cache. |
