data "aws_region" "current" {}

locals {
  name = "portfolio-${var.env}-session-box"

  # Only the t-family is burstable. Standard credit mode stops surplus CPU credits from billing.
  is_burstable = startswith(var.instance_type, "t")
}

resource "aws_instance" "box" {
  ami                         = var.ami_id
  instance_type               = var.instance_type
  subnet_id                   = var.subnet_id
  vpc_security_group_ids      = var.security_group_ids
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
  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = var.root_volume_gb
    encrypted   = true
  }

  tags = {
    Name        = local.name
    Project     = "portfolio-data-platform"
    Environment = var.env
    ManagedBy   = "terraform"
  }
}

# Starts the box at 10:00 UTC every night (3 a.m. Arizona, 6 a.m. US Eastern).
resource "aws_scheduler_schedule" "start" {
  name                         = "${local.name}-start"
  description                  = "Starts the session box for the nightly pipeline run."
  schedule_expression          = "cron(0 10 * * ? *)"
  schedule_expression_timezone = "UTC"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ec2:startInstances"
    role_arn = var.scheduler_role_arn
    input    = jsonencode({ InstanceIds = [aws_instance.box.id] })
  }
}

# Hard stop four hours after the 10:00 UTC start. It is the session limit: even if the
# pipelines hang, the box stops at 14:00 UTC.
resource "aws_scheduler_schedule" "hard_stop" {
  name                         = "${local.name}-hard-stop"
  description                  = "Stops the session box four hours after its start, whatever the pipelines are doing."
  schedule_expression          = "cron(0 14 * * ? *)"
  schedule_expression_timezone = "UTC"

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
  treat_missing_data  = "breaching"
  alarm_actions       = ["arn:aws:automate:${data.aws_region.current.name}:ec2:stop"]

  dimensions = {
    InstanceId = aws_instance.box.id
  }
}
