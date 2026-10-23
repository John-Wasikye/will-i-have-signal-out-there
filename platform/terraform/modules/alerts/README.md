# alerts module

I use this module to get an email when a run goes wrong (ADR-0024, PR-14). It creates one SNS topic per environment, named `portfolio-<env>-run-alerts`, and subscribes each address in `alert_emails` to it. AWS sends each address a confirmation email, and nothing arrives until the link in it is clicked.

Four things send an email through the topic:

- **A task fails.** Airflow's failure callback records the incident and then emails me (`pipelines/platform/publish/alerts.py`).
- **A run leaves a pipeline late or failed.** The `report_run` task reads `status.json` after the upload. The publish gate can refuse a run without any task failing, so the failure callback alone would miss this.
- **The box watchdog stops a run** at the 2-hour maximum or for a spot warning. The box powers off, so no task fails and the run never reports; the watchdog sends the email itself (`platform/box/box_watchdog.py`).
- **No good run arrives in time.** Each good run records one data point, `GoodRunPublished` in the `Portfolio/Platform` namespace, for each pipeline that is ok. For each pipeline in `watched_pipelines`, an alarm fires when no data point arrives for `freshness_target_hours` hours in a row. Missing data counts as a missed run, so the alarm also catches a box that never started, which nothing on the box can report. The bucket size alarms use the same topic.

`watched_pipelines` is empty by default, because dev has no nightly schedule and the alarm would fire every day. `envs/live` watches every pipeline in `pipeline_names`.

The topic is not encrypted with a key. A CloudWatch alarm cannot publish to a topic encrypted with the AWS-managed SNS key, and a key of my own costs a dollar a month. The messages hold a task name and a short error, never a key or personal data, and the email itself is not encrypted anyway.

The box gets `publish_policy_json` through the `box_iam` module. It can publish to its own topic and write metrics to the `Portfolio/Platform` namespace only. It cannot subscribe anyone or change the topic. CloudWatch cannot limit metric writes to one environment, so a dev box could in principle write a live data point. That gap is small, because dev roles reach no live data.

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `env` | string | none | `dev` or `live`. |
| `alert_emails` | list(string) | `[]` | Alert recipients. |
| `watched_pipelines` | list(string) | `[]` | Pipelines that get a missed-run alarm. |
| `freshness_target_hours` | number | 26 | Hours without a good run before the alarm fires, 1 to 168 (OQ-P08). |

## Outputs

| Name | Description |
|---|---|
| `topic_arn` | ARN of the topic. The install script takes it as `ALERT_TOPIC_ARN`. |
| `publish_policy_json` | Policy for the box. Pass it to the `box_iam` module. |
