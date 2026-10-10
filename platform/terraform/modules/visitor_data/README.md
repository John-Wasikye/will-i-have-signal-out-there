# visitor_data module

Creates the DynamoDB table that holds visitor data for one environment. The table is named `portfolio-<env>-visitor`, with string hash key `pk` and string range key `sk`.

Billing is provisioned, with 5 read and 5 write units, which stays inside the free tier. Point-in-time recovery and server-side encryption are on. Live tables have deletion protection on, and dev tables do not.

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `env` | string | none | `dev` or `live`. |

## Outputs

| Name | Description |
|---|---|
| `table_name` | Name of the visitor table. |
| `table_arn` | ARN of the visitor table. |
