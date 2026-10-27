data "aws_region" "current" {}

locals {
  name = "portfolio-${var.env}-session-box"

  # Only the t-family is burstable. Standard credit mode stops surplus CPU credits from billing.
  is_burstable = startswith(var.instance_type, "t")
}

data "aws_subnet" "box" {
  id = var.subnet_id
}

# The box's own security group. Without one, AWS gives the box the VPC's default group, which
# lets in traffic from everything else in that group, other projects included. This group lets
# nothing in: I reach the box through Session Manager, which needs no open port. The rules are
# written here, so an inbound rule added by hand is removed by the next apply.
resource "aws_security_group" "box" {
  name        = local.name
  description = "The ${var.env} session box: no inbound traffic, any outbound."
  vpc_id      = data.aws_subnet.box.vpc_id

  ingress = []

  # Outbound only: the box pulls images, installs packages and calls AWS services.
  egress {
    description = "Any outbound traffic."
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "box" {
  ami                         = var.ami_id
  instance_type               = var.instance_type
  subnet_id                   = var.subnet_id
  vpc_security_group_ids      = concat([aws_security_group.box.id], var.security_group_ids)
  iam_instance_profile        = var.instance_profile_name
  associate_public_ip_address = true # No NAT gateway, so the box needs a public address to pull images.

  # Spot only. A persistent request lets the box be stopped and started again each night.
  # A two-minute interruption stops the box, and every job is safe to rerun.
  instance_market_options {
    market_type = "spot"

    spot_options {
      spot_instance_type             = "persistent"
      instance_interruption_behavior = "stop"
    }
  }

  dynamic "credit_specification" {
    for_each = local.is_burstable ? [1] : []

    content {
      cpu_credits = "standard"
    }
  }

  # Require IMDSv2, so a request from inside a container cannot read instance credentials.
  # Tags are readable there too: the watchdog reads WorkSessionUntil to tell a work session I
  # planned from a start nobody planned.
  metadata_options {
    http_endpoint          = "enabled"
    http_tokens            = "required"
    instance_metadata_tags = "enabled"
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = var.root_volume_gb
    encrypted   = true
  }

  # Project, Environment and ManagedBy come from the provider's default tags in envs/.
  tags = {
    Name = local.name
  }

  # I set WorkSessionUntil by hand when I start a work session, so Terraform must not remove it.
  # A stopped box gives up its public address, and AWS then reports associate_public_ip_address
  # as false, so every plan made while the box is off would replace it. The subnet gives the box
  # a new address at each start, so the setting matters only when the box is created.
  lifecycle {
    ignore_changes = [
      associate_public_ip_address,
      tags["WorkSessionUntil"],
      tags_all["WorkSessionUntil"],
    ]
  }
}

# Starts the box at 10:00 UTC every night (3 a.m. Arizona, 6 a.m. US Eastern).
resource "aws_scheduler_schedule" "start" {
  name                         = "${local.name}-start"
  description                  = "Starts the session box for the nightly pipeline run."
  schedule_expression          = "cron(0 10 * * ? *)"
  schedule_expression_timezone = "UTC"
  state                        = var.schedule_enabled ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ec2:startInstances"
    role_arn = var.scheduler_role_arn
    input    = jsonencode({ InstanceIds = [aws_instance.box.id] })

    # With no spot capacity the start fails. The default policy retries for 24 hours, which
    # once started the box at 15:41 UTC, after the hard stop. Giving up after 2 hours means a
    # 2-hour run still ends by 14:00 UTC; otherwise the night is skipped.
    retry_policy {
      maximum_event_age_in_seconds = 7200
      maximum_retry_attempts       = 185
    }
  }
}

# Hard stop four hours after the 10:00 UTC start. It is the session limit: even if the
# pipelines hang, the box stops at 14:00 UTC.
resource "aws_scheduler_schedule" "hard_stop" {
  name                         = "${local.name}-hard-stop"
  description                  = "Stops the session box four hours after its start, whatever the pipelines are doing."
  schedule_expression          = "cron(0 14 * * ? *)"
  schedule_expression_timezone = "UTC"
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ec2:stopInstances"
    role_arn = var.scheduler_role_arn
    input    = jsonencode({ InstanceIds = [aws_instance.box.id] })
  }
}

# Stops the box after the CPU has stayed below the idle threshold. The alarm action is the
# built-in EC2 stop action, so no Lambda function is needed for this guard.
#
# An alarm acts only when it moves into ALARM. A stopped box sends no CPU data, so missing data
# leaves the alarm waiting (INSUFFICIENT_DATA) rather than already in ALARM. After the next
# boot, idle periods then move it into ALARM, and that move stops the box.
resource "aws_cloudwatch_metric_alarm" "idle" {
  alarm_name          = "${local.name}-idle"
  alarm_description   = "Stops the session box when it has been idle. Budget alerts lag, so this is a real cost guard."
  namespace           = "AWS/EC2"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = var.idle_evaluation_periods
  threshold           = var.idle_cpu_percent
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "missing"
  alarm_actions       = ["arn:aws:automate:${data.aws_region.current.name}:ec2:stop"]

  dimensions = {
    InstanceId = aws_instance.box.id
  }
}
