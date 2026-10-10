# catalog module

Creates one AWS Glue catalog database for an environment. The database is named `portfolio_dev` or `portfolio_live`. Glue names cannot contain hyphens, so underscores are used here.

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `env` | string | none | `dev` or `live`. |

## Outputs

| Name | Description |
|---|---|
| `database_name` | Name of the Glue database. |
| `database_arn` | ARN of the Glue database. |
