# budget module

I use this module to create the monthly cost budget `portfolio-monthly` for the whole AWS account. The default limit is $40.

Alerts go to `alert_emails` at 80 percent of actual spend and at 100 percent of forecast spend. With an empty list, the budget still exists and tracks spend, but it sends no alerts.

I do not configure budget actions that deny new launches. They are a backup only. The 4-hour session limit and the idle alarm are the real guards, because budget alerts can lag by hours.

I call this module only from `envs/live`. Budget names are unique per account, so a second call would clash.

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `limit_usd` | number | 40 | Monthly limit in US dollars. |
| `alert_emails` | list(string) | `[]` | Alert recipients. |

## Outputs

| Name | Description |
|---|---|
| `budget_name` | Name of the budget. |
