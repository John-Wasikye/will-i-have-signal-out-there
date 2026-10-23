# parameters module

I use this module to build the IAM policy that lets pipeline roles read Parameter Store for one environment. The policy covers `/portfolio/<env>/*`.

This module creates no parameters and holds no secret values. Parameter values are written by hand or by a pipeline at run time, so they never reach Terraform state. The path convention is `/portfolio/<env>/<project>/<name>`.

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `env` | string | none | `dev` or `live`. |

## Outputs

| Name | Description |
|---|---|
| `read_policy_json` | JSON policy document for reading parameters under the environment path. |
| `parameter_path_prefix` | Path prefix for the environment, for example `/portfolio/dev`. |
