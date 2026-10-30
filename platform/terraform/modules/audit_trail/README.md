# audit_trail module

I use this module to keep the account's security logs: one CloudTrail trail, `portfolio-live-audit`, and its own bucket, `portfolio-live-audit-<account>`. A trail covers the whole account, so `envs/live` is the only caller, and it logs dev and live alike.

What it records:

- **Every management event, reads included,** in every region, plus global services such as IAM. That covers every change to the account and every read of a key, Parameter Store reads included (security-and-privacy.md). The first trail's management events are free.
- **No data events.** Recording each S3 object read would be billed per event, and the platform has no need for it.
- **Log file validation is on,** so CloudTrail writes digest files and a changed or deleted log can be detected.

How the logs are kept (requirements PR-20, ADR-0019):

- Security logs are kept one year, then removed. Old versions go after 30 days, and failed uploads are cleaned up after 7 days.
- The bucket is private, encrypted, versioned, and refuses requests that are not encrypted in transit. Only this trail can write to it, and only under `AWSLogs/<account>/`.
- A destroy never deletes the logs: the bucket is not emptied on destroy, so it must be emptied by hand first.
- A size alarm sends to `alarm_actions`. `envs/live` passes the run alerts topic.

It also turns on IAM Access Analyzer (external access, the free kind) for the account, `portfolio-live-external-access`. It lists every bucket, role, key or function that can be reached from outside the account, in the console under IAM, Access Analyzer.

The names start with `portfolio-live-`, so the dev apply role is refused them (see the `github_roles` module).

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `size_alarm_bytes` | number | 10 GB | Size that raises the bucket size alarm. |
| `alarm_actions` | list(string) | `[]` | Targets notified by the size alarm. |

## Outputs

| Name | Description |
|---|---|
| `trail_arn` | ARN of the trail. |
| `bucket_name` | Bucket that holds the security logs. |
