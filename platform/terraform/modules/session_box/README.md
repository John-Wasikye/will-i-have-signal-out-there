# session_box module

I use this module to create the session box: the one computer that runs the nightly pipelines. It is a spot instance, so it costs little, and it is stopped whenever it is not needed.

What the module creates:

- **The box:** a spot instance using a persistent request, so it can be stopped and started again. A spot interruption stops the box rather than ending it, because every job is safe to rerun. A `t4g` box runs in standard credit mode, so surplus CPU never bills. An `m7g` box is not burstable, so it has no credit setting.
- **A start at 10:00 UTC:** an EventBridge Scheduler schedule starts the box every night. That is 3 a.m. in Arizona and 6 a.m. in US Eastern. When there is no spot capacity, the schedule retries for up to 2 hours and then gives up, so a 2-hour run still ends before the hard stop and a late start never happens.
- **A hard stop at 14:00 UTC:** a second schedule stops the box four hours after the start, whatever the pipelines are doing. This is my session limit.
- **Its own security group:** no inbound traffic and any outbound. Without it, AWS would give the box the VPC's default group, which lets in traffic from everything else in that group, including other projects in the account. I reach the box through Session Manager, which needs no open port.
- **An idle stop:** a CloudWatch alarm stops the box when its CPU stays below a threshold. The alarm uses EC2's built-in stop action, so it needs no Lambda function. A stopped box sends no data, and the alarm treats that as missing rather than idle: an alarm acts only when it moves into ALARM, so if a stopped box left it already in ALARM, a box started and then left idle would never be stopped.

What the module does not do: it does not install k3s, Airflow or Spark; `platform/box/install.sh` does that, on the box. The box watchdog, which the install script starts, stops the box at the 2-hour nightly maximum, at the 4-hour limit for a session I start by hand, and on the two-minute spot warning.

## Decisions I made

- **Persistent spot requests, not one-time.** A one-time spot instance cannot be stopped and started again, so the nightly start would fail.
- **The idle threshold is a placeholder.** The default is 5 percent average CPU for 6 five-minute periods. I will replace it after measuring the real box (open question OQ-P02).
- **Public address, no NAT gateway.** The box pulls its images from the internet, and a NAT gateway would cost more than the box does.
- **IMDSv2 required.** A container on the box cannot read the instance's credentials through the old metadata endpoint.

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `env` | string | none | `dev` or `live`. |
| `instance_type` | string | `t4g.2xlarge` | `t4g.2xlarge` or `m7g.2xlarge`. |
| `ami_id` | string | none | An arm64 image. Check its manifest before the first use. |
| `subnet_id` | string | none | A public subnet. |
| `security_group_ids` | list(string) | `[]` | Extra groups on top of the box's own. Usually empty. |
| `instance_profile_name` | string | none | Instance profile with read access to Parameter Store and to the box's buckets. |
| `scheduler_role_arn` | string | none | Role that the scheduler assumes to start and stop the box. The `box_iam` module creates it. |
| `schedule_enabled` | bool | `true` | Whether the box starts by itself every night. I turn it off in dev. The hard stop stays on either way. |
| `root_volume_gb` | number | 50 | Root disk size. Project data is never stored here. |
| `idle_cpu_percent` | number | 5 | Placeholder idle threshold. |
| `idle_evaluation_periods` | number | 6 | Placeholder number of idle periods before the stop. |

## Outputs

| Name | Description |
|---|---|
| `instance_id` | ID of the session box. |
| `idle_alarm_name` | Name of the idle alarm. |
