# storage module

I use this module to create the three S3 buckets for one environment: raw, lake and site.

Every bucket has versioning, a public access block, default AES-256 encryption, and a policy that denies requests without TLS. Every bucket has the clean-up rules from my platform requirements (PR-20). Pipelines write temporary files under `tmp/`, Spark checkpoints under `checkpoints/`, and logs under `logs/`.

Dev raw and lake data expire after 14 days. The live raw bucket has Object Lock in governance mode for 30 days. Object Lock must be set when a bucket is created, so I cannot add it later. Dev buckets are created with `force_destroy`, so they can be torn down cheaply.

Each bucket has a CloudWatch alarm on its size. The alarm fires when the size passes `size_alarm_bytes`.

Bucket names look like `portfolio-<env>-raw-<account-id>`.

A bucket has only one policy, so every rule for a bucket lives in one policy document. Each bucket denies requests without TLS. The site bucket also lets one CloudFront distribution read it, once I pass that distribution's ARN. I build the bucket ARNs from the names, so a plan shows the full policies and the tests can check them.

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `env` | string | none | `dev` or `live`. |
| `size_alarm_bytes` | number | 100 GB | Size in bytes that raises the size alarm. |
| `alarm_actions` | list(string) | `[]` | Targets notified by the size alarm. |
| `site_distribution_arn` | string | `null` | The CloudFront distribution that serves the site. When set, only this distribution may read the site bucket. |

## Outputs

| Name | Description |
|---|---|
| `bucket_names` | Map of `raw`, `lake` and `site` to bucket name. |
| `bucket_arns` | Map of `raw`, `lake` and `site` to bucket ARN. |
