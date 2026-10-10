# Plan-only tests with a mock AWS provider. No AWS calls are made.
# Run from the module folder: terraform init -backend=false, then terraform test.

mock_provider "aws" {
  mock_data "aws_region" {
    defaults = {
      name = "us-east-1"
    }
  }
}

variables {
  scheduler_role_arn = "arn:aws:iam::123456789012:role/portfolio-dev-scheduler"
}

run "runs_on_a_persistent_spot_request_that_stops_on_interruption" {
  command = plan

  variables {
    env                   = "dev"
    ami_id                = "ami-0123456789abcdef0"
    subnet_id             = "subnet-0123456789abcdef0"
    instance_profile_name = "portfolio-dev-session-box"
  }

  assert {
    condition     = aws_instance.box.instance_market_options[0].market_type == "spot"
    error_message = "The session box must run on spot capacity."
  }

  assert {
    condition     = aws_instance.box.instance_market_options[0].spot_options[0].spot_instance_type == "persistent"
    error_message = "The box must use a persistent spot request, so it can be started again each night."
  }

  assert {
    condition     = aws_instance.box.instance_market_options[0].spot_options[0].instance_interruption_behavior == "stop"
    error_message = "A spot interruption must stop the box, not end it, because every job is safe to rerun."
  }
}

run "starts_each_night_at_1000_utc" {
  command = plan

  variables {
    env                   = "dev"
    ami_id                = "ami-0123456789abcdef0"
    subnet_id             = "subnet-0123456789abcdef0"
    instance_profile_name = "portfolio-dev-session-box"
    scheduler_role_arn    = "arn:aws:iam::123456789012:role/portfolio-dev-scheduler"
  }

  assert {
    condition     = aws_scheduler_schedule.start.schedule_expression == "cron(0 10 * * ? *)"
    error_message = "The box must start at 10:00 UTC every night."
  }

  assert {
    condition     = aws_scheduler_schedule.start.schedule_expression_timezone == "UTC"
    error_message = "The schedule must use UTC."
  }

  assert {
    condition     = strcontains(aws_scheduler_schedule.start.target[0].arn, "ec2:startInstances")
    error_message = "The start schedule must call EC2 startInstances."
  }
}

run "hard_stop_ends_the_session_four_hours_after_start" {
  command = plan

  variables {
    env                   = "dev"
    ami_id                = "ami-0123456789abcdef0"
    subnet_id             = "subnet-0123456789abcdef0"
    instance_profile_name = "portfolio-dev-session-box"
    scheduler_role_arn    = "arn:aws:iam::123456789012:role/portfolio-dev-scheduler"
  }

  assert {
    condition     = aws_scheduler_schedule.hard_stop.schedule_expression == "cron(0 14 * * ? *)"
    error_message = "The hard stop must be 14:00 UTC, four hours after the 10:00 start."
  }

  assert {
    condition     = strcontains(aws_scheduler_schedule.hard_stop.target[0].arn, "ec2:stopInstances")
    error_message = "The hard stop schedule must call EC2 stopInstances."
  }
}

run "burstable_box_uses_standard_credit_mode" {
  command = plan

  variables {
    env                   = "dev"
    ami_id                = "ami-0123456789abcdef0"
    subnet_id             = "subnet-0123456789abcdef0"
    instance_profile_name = "portfolio-dev-session-box"
    instance_type         = "t4g.2xlarge"
  }

  assert {
    condition     = aws_instance.box.credit_specification[0].cpu_credits == "standard"
    error_message = "A t4g box must use standard credit mode, so it never bills for surplus credits."
  }
}

run "heavy_batch_box_has_no_credit_setting" {
  command = plan

  variables {
    env                   = "dev"
    ami_id                = "ami-0123456789abcdef0"
    subnet_id             = "subnet-0123456789abcdef0"
    instance_profile_name = "portfolio-dev-session-box"
    instance_type         = "m7g.2xlarge"
  }

  assert {
    condition     = length(aws_instance.box.credit_specification) == 0
    error_message = "An m7g box is not burstable, so it must not set a credit mode."
  }
}

run "idle_alarm_stops_the_box" {
  command = plan

  variables {
    env                   = "dev"
    ami_id                = "ami-0123456789abcdef0"
    subnet_id             = "subnet-0123456789abcdef0"
    instance_profile_name = "portfolio-dev-session-box"
  }

  assert {
    condition     = contains(aws_cloudwatch_metric_alarm.idle.alarm_actions, "arn:aws:automate:us-east-1:ec2:stop")
    error_message = "The idle alarm must stop the box."
  }

  assert {
    condition     = aws_cloudwatch_metric_alarm.idle.metric_name == "CPUUtilization"
    error_message = "The idle alarm must watch CPU use."
  }
}

run "rejects_an_instance_size_outside_the_plan" {
  command = plan

  variables {
    env                   = "dev"
    ami_id                = "ami-0123456789abcdef0"
    subnet_id             = "subnet-0123456789abcdef0"
    instance_profile_name = "portfolio-dev-session-box"
    instance_type         = "c7g.16xlarge"
  }

  expect_failures = [
    var.instance_type,
  ]
}

run "rejects_an_unknown_environment" {
  command = plan

  variables {
    env                   = "staging"
    ami_id                = "ami-0123456789abcdef0"
    subnet_id             = "subnet-0123456789abcdef0"
    instance_profile_name = "portfolio-dev-session-box"
  }

  expect_failures = [
    var.env,
  ]
}

run "schedules_are_enabled_by_default" {
  command = plan

  variables {
    env                   = "live"
    ami_id                = "ami-0123456789abcdef0"
    subnet_id             = "subnet-0123456789abcdef0"
    instance_profile_name = "portfolio-live-session-box"
  }

  assert {
    condition     = aws_scheduler_schedule.start.state == "ENABLED" && aws_scheduler_schedule.hard_stop.state == "ENABLED"
    error_message = "The start and the hard stop must be enabled by default."
  }
}

run "dev_can_turn_the_nightly_schedule_off" {
  command = plan

  variables {
    env                   = "dev"
    ami_id                = "ami-0123456789abcdef0"
    subnet_id             = "subnet-0123456789abcdef0"
    instance_profile_name = "portfolio-dev-session-box"
    schedule_enabled      = false
  }

  assert {
    condition     = aws_scheduler_schedule.start.state == "DISABLED"
    error_message = "With the schedule off, the box must not start by itself."
  }

  assert {
    condition     = aws_scheduler_schedule.hard_stop.state == "ENABLED"
    error_message = "The hard stop must stay on even when the nightly start is off, so a box I start by hand still stops."
  }
}
