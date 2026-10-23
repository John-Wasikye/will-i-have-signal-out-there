data "aws_partition" "current" {}

data "aws_region" "current" {}

data "aws_caller_identity" "current" {}

locals {
  topic_name = "portfolio-${var.env}-run-alerts"
  # Built from its parts, so the ARN is known at plan time and the box policy can name it.
  topic_arn = "arn:${data.aws_partition.current.partition}:sns:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:${local.topic_name}"

  # Must match METRIC_NAMESPACE and METRIC_NAME in pipelines/platform/publish/alerts.py.
  metric_namespace = "Portfolio/Platform"
  metric_name      = "GoodRunPublished"
}

# Not encrypted with a key. A CloudWatch alarm cannot publish to a topic encrypted with the
# AWS-managed SNS key, and a key of my own costs a dollar a month. The messages hold a task
# name and a short error, never a key or personal data, and email is not encrypted anyway.
#trivy:ignore:AVD-AWS-0095
resource "aws_sns_topic" "run_alerts" {
  name = local.topic_name
}

# AWS emails each address a link. The subscription does nothing until the link is clicked.
# The addresses are sensitive, and Terraform cannot name resources after a sensitive value, so
# the subscriptions are counted. Only the number of addresses shows in a plan.
resource "aws_sns_topic_subscription" "email" {
  count = nonsensitive(length(var.alert_emails))

  topic_arn = aws_sns_topic.run_alerts.arn
  protocol  = "email"
  endpoint  = var.alert_emails[count.index]
}

# The box records one data point per good run. If the box never starts, nothing on it can
# send an email, so this alarm does: missing data counts as a missed run. Hourly periods
# let the alarm fire at the freshness target instead of at a day boundary.
resource "aws_cloudwatch_metric_alarm" "no_good_run" {
  for_each = toset(var.watched_pipelines)

  alarm_name        = "portfolio-${var.env}-${each.value}-no-good-run"
  alarm_description = "No good run of ${each.value} in ${var.env} for ${var.freshness_target_hours} hours, so its data is late."

  namespace   = local.metric_namespace
  metric_name = local.metric_name
  dimensions = {
    Environment = var.env
    Pipeline    = each.value
  }

  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = var.freshness_target_hours
  datapoints_to_alarm = var.freshness_target_hours
  comparison_operator = "LessThanThreshold"
  threshold           = 1
  treat_missing_data  = "breaching"

  alarm_actions = [local.topic_arn]

  depends_on = [aws_sns_topic.run_alerts]
}

# The box can send alerts and record good runs. It cannot change the topic or who gets the
# emails. PutMetricData cannot be limited to a resource, so it is limited to one namespace.
data "aws_iam_policy_document" "publish" {
  statement {
    sid       = "SendRunAlerts"
    effect    = "Allow"
    actions   = ["sns:Publish"]
    resources = [local.topic_arn]
  }

  statement {
    sid       = "RecordGoodRuns"
    effect    = "Allow"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = [local.metric_namespace]
    }
  }
}
