# budget module

Creates the monthly cost budget `portfolio-monthly` for the whole AWS account, with a $40 limit by default.

Alerts go to `alert_emails` at 80 percent of actual spend and at 100 percent of forecast spend. With an empty list, the budget still exists and tracks spend, but it sends no alerts.

Budget actions that deny new launches are a backup and are not configured here. The 4-hour session limit and the idle alarm are the real guards.

Call this module only from `envs/live`. Budget names are unique per account, so a second call would clash.

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `limit_usd` | number | 40 | Monthly limit in US dollars. |
| `alert_emails` | list(string) | `[]` | Alert recipients. |

## Outputs

| Name | Description |
|---|---|
| `budget_name` | Name of the budget. |
