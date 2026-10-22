# box_iam module

I use this module to give the session box its permissions, and to let the scheduler start and stop it. It creates two roles.

**The box role.** The box assumes it through an instance profile. It can:

- do everything a pipeline role can do with this environment's raw and lake buckets and Glue database. I reuse the `data_access_policy_json` output of the `iam` module, so the rules live in one place.
- read Parameter Store under `/portfolio/<env>/*`, using the policy from the `parameters` module.
- read and write files in this environment's site bucket, but not delete them. This is where the box publishes the gold Parquet files and `status.json`.
- pull the Airflow image from this environment's repository, but not push. A precondition refuses a repository from the wrong environment.
- send run alerts through this environment's SNS topic and record good runs in CloudWatch, using the policy from the `alerts` module. A precondition refuses a topic from the wrong environment.
- connect through Session Manager, so I can open a shell from the browser and no SSH port is open.

A precondition refuses a site bucket from the wrong environment, so a dev box can never get a live bucket.

**The scheduler role.** EventBridge Scheduler assumes it, and only from this AWS account. It can start and stop instances, and only instances whose `Name` tag is `portfolio-<env>-session-box`. It cannot create or end instances.

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `env` | string | none | `dev` or `live`. |
| `site_bucket_arn` | string | none | This environment's site bucket. |
| `data_access_policy_json` | string | none | From the `iam` module's `data_access_policy_json` output. |
| `parameter_read_policy_json` | string | none | From the `parameters` module. |
| `registry_arn` | string | none | This environment's image repository, from the `registry` module. |
| `alert_policy_json` | string | none | From the `alerts` module's `publish_policy_json` output. |

## Outputs

| Name | Description |
|---|---|
| `instance_profile_name` | Pass to the `session_box` module. |
| `scheduler_role_arn` | Pass to the `session_box` module. |
