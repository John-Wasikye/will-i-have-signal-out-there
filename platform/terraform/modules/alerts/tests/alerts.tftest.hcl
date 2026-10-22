# Plan-only tests. No AWS calls are made.
# The real provider runs so the policy document builds real JSON. Only the three lookups
# that need an AWS account are overridden with fixed values, for every run in this file.
# Run from the module folder: terraform init -backend=false, then terraform test.

provider "aws" {
  region                      = "us-east-1"
  access_key                  = "not-a-real-key"
  secret_key                  = "not-a-real-secret"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
}

override_data {
  target = data.aws_caller_identity.current
  values = {
    account_id = "123456789012"
  }
}

override_data {
  target = data.aws_partition.current
  values = {
    partition = "aws"
  }
}

override_data {
  target = data.aws_region.current
  values = {
    name = "us-east-1"
  }
}

variables {
  env = "dev"
}

run "topic_is_named_after_the_environment" {
  command = plan

  assert {
    condition     = aws_sns_topic.run_alerts.name == "portfolio-dev-run-alerts"
    error_message = "The topic must be named portfolio-<env>-run-alerts."
  }

  assert {
    condition     = output.topic_arn == "arn:aws:sns:us-east-1:123456789012:portfolio-dev-run-alerts"
    error_message = "The topic ARN must be known at plan time, so the box policy can name it."
  }
}

run "no_subscription_without_an_email_address" {
  command = plan

  assert {
    condition     = length(aws_sns_topic_subscription.email) == 0
    error_message = "With no alert emails, the topic must have no subscriptions."
  }
}

run "each_email_address_gets_one_email_subscription" {
  command = plan

  variables {
    alert_emails = ["alerts@example.com", "backup@example.com"]
  }

  assert {
    condition     = length(aws_sns_topic_subscription.email) == 2
    error_message = "Each alert email must get one subscription."
  }

  assert {
    condition     = alltrue([for s in aws_sns_topic_subscription.email : s.protocol == "email"])
    error_message = "Every subscription must be an email subscription."
  }
}

run "no_missed_run_alarm_unless_a_pipeline_is_watched" {
  command = plan

  assert {
    condition     = length(aws_cloudwatch_metric_alarm.no_good_run) == 0
    error_message = "Dev has no nightly schedule, so by default no pipeline is watched."
  }
}

run "missed_run_alarm_fires_when_no_good_run_arrives_within_the_target" {
  command = plan

  variables {
    watched_pipelines = ["platform_skeleton"]
  }

  assert {
    condition     = aws_cloudwatch_metric_alarm.no_good_run["platform_skeleton"].treat_missing_data == "breaching"
    error_message = "No data point at all must count as a missed run, because the box may never start."
  }

  assert {
    condition     = aws_cloudwatch_metric_alarm.no_good_run["platform_skeleton"].period * aws_cloudwatch_metric_alarm.no_good_run["platform_skeleton"].evaluation_periods == 26 * 3600
    error_message = "The alarm must look back over the 26-hour freshness target."
  }

  assert {
    condition     = aws_cloudwatch_metric_alarm.no_good_run["platform_skeleton"].datapoints_to_alarm == aws_cloudwatch_metric_alarm.no_good_run["platform_skeleton"].evaluation_periods
    error_message = "The alarm must fire only when every hour in the target had no good run."
  }

  assert {
    condition     = aws_cloudwatch_metric_alarm.no_good_run["platform_skeleton"].namespace == "Portfolio/Platform" && aws_cloudwatch_metric_alarm.no_good_run["platform_skeleton"].metric_name == "GoodRunPublished"
    error_message = "The alarm must read the metric that pipelines/platform/publish/alerts.py writes."
  }

  assert {
    condition     = aws_cloudwatch_metric_alarm.no_good_run["platform_skeleton"].dimensions == tomap({ Environment = "dev", Pipeline = "platform_skeleton" })
    error_message = "The alarm must watch one pipeline in this environment only."
  }

  assert {
    condition     = aws_cloudwatch_metric_alarm.no_good_run["platform_skeleton"].alarm_actions == toset(["arn:aws:sns:us-east-1:123456789012:portfolio-dev-run-alerts"])
    error_message = "The alarm must email through the run alerts topic."
  }
}

run "box_can_publish_to_its_own_topic_and_write_only_platform_metrics" {
  command = plan

  assert {
    condition     = strcontains(output.publish_policy_json, "sns:Publish") && strcontains(output.publish_policy_json, "portfolio-dev-run-alerts")
    error_message = "The box must be able to publish to this environment's topic."
  }

  assert {
    condition     = strcontains(output.publish_policy_json, "cloudwatch:PutMetricData") && strcontains(output.publish_policy_json, "Portfolio/Platform")
    error_message = "The box must be able to write metrics, limited to the Portfolio/Platform namespace."
  }

  assert {
    condition     = !strcontains(output.publish_policy_json, "sns:Subscribe") && !strcontains(output.publish_policy_json, "sns:SetTopicAttributes")
    error_message = "The box must not be able to change who gets the alerts."
  }
}

run "rejects_an_unknown_environment" {
  command = plan

  variables {
    env = "staging"
  }

  expect_failures = [
    var.env,
  ]
}

run "rejects_a_freshness_target_longer_than_a_week" {
  command = plan

  variables {
    freshness_target_hours = 169
  }

  expect_failures = [
    var.freshness_target_hours,
  ]
}
