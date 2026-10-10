# catalog module

I use this module to create one AWS Glue catalog database for each environment. The database is named `portfolio_dev` or `portfolio_live`. Glue names cannot contain hyphens, so I use underscores.

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `env` | string | none | `dev` or `live`. |

## Outputs

| Name | Description |
|---|---|
| `database_name` | Name of the Glue database. |
| `database_arn` | ARN of the Glue database. |
