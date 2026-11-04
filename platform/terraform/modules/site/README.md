# site module

I use this module to put the website on CloudFront. The site files live in a private S3 bucket, and CloudFront is the only thing that can read them.

What it does:

- **Private access.** CloudFront signs every request to the bucket. The storage module's bucket policy lets only this distribution read the site bucket.
- **HTTPS only.** Requests on plain http are redirected to https.
- **Security headers on every response.** Browsers are told to use https for a year (HSTS, HTTP Strict Transport Security), not to guess file types, never to show the site inside another site's frame, and to send only the site's address as the referrer. The content security policy lets the page load only its own files and call API Gateway addresses in this region, so injected outside scripts do not run.
- **A fresh status page.** `status.json` is never cached, so the status page always shows the latest run. Everything else uses the managed caching policy.
- **No public data files.** The Lambda function reads the Parquet files in `published/` directly from the bucket. Readers have no use for them, so a small CloudFront function answers 403 for any request under `published/`.
- **Page links work.** S3 answers 403 for a missing file when access is private. A missing path returns `index.html` with a 200, so the app can handle its own page links.
- **The cheapest price class,** `PriceClass_100`, which stays inside CloudFront's free allowance for my traffic.

Without a custom domain, the site uses the default `cloudfront.net` address and certificate.

## Custom domain in two phases

The site can also be served under its own domain. An ACM (AWS Certificate Manager) certificate proves to AWS that I own the domain. CloudFront only accepts certificates from `us-east-1`, which is where this module's configuration runs. DNS for `johnwasikye.com` is at Cloudflare, so I add the records there by hand. Each record must be "DNS only" (grey cloud), not proxied, or AWS cannot check it.

Phase 1 requests the certificate. Set `site_domain` and leave `attach_domain` false. `envs/live` did this first, and is now in phase 2.

1. Apply. Terraform requests the certificate and does not wait for it.
2. Read the output `dns_record_1_certificate_validation`. Add the CNAME it shows at Cloudflare, as DNS only. AWS uses it to check the domain.
3. Wait until the certificate shows as issued in ACM in `us-east-1`.

Phase 2 serves the site under the domain. It is a separate change, made after phase 1 is complete.

1. In `envs/live/main.tf`, set `attach_domain = true`. The serving module's `allowed_origins` is `module.site.origins`, which then adds `https://<site_domain>`, so the API accepts requests from the new address too.
2. Apply. The apply waits for the certificate to be issued. If the validation record is missing, the apply fails after 10 minutes, and CloudFront keeps its default certificate. Once the apply succeeds, CloudFront serves the domain with the certificate. The `cloudfront.net` address keeps working.
3. Read the output `dns_record_2_site`. Add that CNAME at Cloudflare, as DNS only. It points the domain at CloudFront.

`attach_domain = true` without `site_domain` is refused.

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `env` | string | none | `dev` or `live`. |
| `bucket_regional_domain_name` | string | none | Regional domain of the site bucket, from the storage module. |
| `site_domain` | string | `null` | Own domain for the site. Null keeps the `cloudfront.net` address. Setting it requests the certificate. |
| `attach_domain` | bool | `false` | True serves the site under `site_domain`. Only set it after the certificate is issued. |

## Outputs

| Name | Description |
|---|---|
| `distribution_arn` | Pass to the storage module as `site_distribution_arn`. |
| `domain_name` | Address of the site. |
| `distribution_id` | ID of the distribution. The deploy workflow clears its cache. |
| `dns_record_1_certificate_validation` | Phase 1 Cloudflare record: the CNAME that validates the certificate. Empty without `site_domain`. |
| `dns_record_2_site` | Phase 2 Cloudflare record: the CNAME from the site domain to CloudFront. Null without `site_domain`. |
| `origins` | Addresses the site is served from, for the serving API's `allowed_origins`: the `cloudfront.net` address, plus `https://<site_domain>` once attached. |
