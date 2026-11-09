# serving module

I use this module to put the FastAPI app on AWS. It creates a Lambda function that runs the app, and an HTTP API in front of it. It works with the session box off, because the function reads only published files.

What it creates:

- **The function:** Python 3.12 on arm64, using the Mangum handler in `handler.py`. It caps how many copies run at once, so a traffic spike cannot run up a bill.
- **The function's role:** it can read files under the `published/` folder of the site bucket, and write its own logs. It cannot write or delete files, and it cannot see the raw or lake buckets.
- **A log group:** logs are kept for 90 days.
- **The HTTP API:** it passes every request to the function, limits the request rate, and allows browser calls only from the origins I list. Browsers may use `GET`, `OPTIONS` and `POST`, and send the `X-Visitor-Id` header for reports. I do not allow a wildcard origin.
- **The report route (C22, `reports.tf`):** `POST /reports` goes to its own function, `reports.handler` from the same package, at 256 MB and 5 seconds (ADR 0029). Its role can only add reports, count limits, read its one key parameter and write its own logs: no delete, scan or query. The route takes 10 requests a second with bursts of 20. Its logs are kept 7 days, and the code logs only the kind of a failure, never the request.
- **Two DynamoDB tables:** `portfolio-<env>-signal-reports` (one item per report, no visitor ID) and `portfolio-<env>-signal-report-limits` (counters keyed by keyed hashes). Both use provisioned capacity inside the free tier, so a flood is throttled instead of billed, expire rows on `expires_at_epoch`, and have point-in-time recovery off so expired rows are really gone (ADR 0012, 0022, 0025, 0026).

## Things to check on the first apply

- A new AWS account can have a low Lambda concurrency quota. If the cap of 10 is refused, I raise the quota or lower the cap.
- The first request after a quiet period is slow. The page tells the reader it may take up to 10 seconds.
- The report function's HMAC key is a SecureString at `/portfolio/<env>/signal/report-visitor-key`. I write it by hand, never in Terraform, so it stays out of state. Until it exists, `POST /reports` answers 503 `dependency_unavailable`.
- The report function has no reserved concurrency: this account's whole Lambda limit is 10, and AWS keeps 10 unreserved.

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `env` | string | none | `dev` or `live`. |
| `published_bucket` | string | none | Site bucket name. The function reads its `published/` folder. |
| `lambda_zip_path` | string | none | Zip with the app, arm64 dependencies and `handler.py`. |
| `lambda_zip_sha256` | string | none | Base64 SHA-256 of the files inside the zip, as `build_package.py` prints it. |
| `allowed_origins` | list(string) | none | Websites that may call the API. No wildcard. |
| `memory_mb` | number | 1024 | Function memory. |
| `timeout_seconds` | number | 30 | Longest request time. |
| `reserved_concurrency` | number | 10 | Most copies running at once. |
| `throttle_rate` | number | 20 | Steady requests per second. |
| `throttle_burst` | number | 40 | Largest burst. |

## Outputs

| Name | Description |
|---|---|
| `api_url` | Base URL of the API. |
| `function_name` | Name of the function. |
| `reports_function_name` | Name of the report function. |
| `report_table_names` | The reports and counters tables. |
| `visitor_key_parameter` | Parameter name of the report function's HMAC key. |

## Building the package

The zip comes from `platform/serving/build_package.py`. I run it from the repository root:

```powershell
python platform/serving/build_package.py
```

It downloads arm64 wheels for Python 3.12, adds the app's Python files, and writes `platform/serving/build/function.zip`. It prints the `lambda_zip_sha256` value to pass to this module. The checksum is taken over the files inside the zip, not the zip's bytes, because the same files compress to different bytes on Windows and Linux. It changes only when the code or the dependencies change, on any machine. The last build was 22.6 MB zipped and 64.7 MB unzipped, well inside Lambda's limits.

The package leaves out `pyarrow` and `boto3`. DuckDB reads Parquet on its own, and the Lambda runtime provides `boto3`.
