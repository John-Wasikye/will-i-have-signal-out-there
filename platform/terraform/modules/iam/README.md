# iam module

Creates one least-privilege IAM role per pipeline, plus the GitHub OIDC provider in the account that creates it.

Roles are named `portfolio-<env>-<pipeline>`. GitHub Actions assumes them through OIDC. Each role can:

* read and write this environment's raw and lake buckets (raw files are never deleted by a pipeline),
* use this environment's Glue database and its tables,
* read Parameter Store under `/portfolio/<env>/*`.

Trust rules: live roles accept only the `main` branch of `github_repo`. Dev roles accept any ref in that repository. Known gap: a dev role can be requested from any branch. The risk is limited because dev roles cannot reach live data.

Only one environment per AWS account should create the OIDC provider. In this repository, `envs/live` creates it and `envs/dev` does not. Apply `envs/live` before `envs/dev` the first time.

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `env` | string | none | `dev` or `live`. |
| `github_repo` | string | `jwasikye/will-i-have-signal-out-there` | Repository allowed to assume the roles. |
| `pipeline_names` | list(string) | `["platform_skeleton"]` | One role per name. |
| `raw_bucket_arn` | string | none | Raw bucket ARN for this environment. |
| `lake_bucket_arn` | string | none | Lake bucket ARN for this environment. |
| `glue_database_name` | string | none | Glue database for this environment. |
| `parameter_read_policy_json` | string | none | Parameter Store read policy from the parameters module. |
| `create_oidc_provider` | bool | `true` | Whether this configuration creates the OIDC provider. |

## Outputs

| Name | Description |
|---|---|
| `role_arns` | Map of pipeline name to role ARN. |
| `oidc_provider_arn` | ARN of the GitHub OIDC provider. |
