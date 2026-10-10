# Plan-only tests. No AWS calls are made.
# The real provider runs so the policy documents build real JSON. Only the three lookups
# that need an AWS account are overridden with fixed values.
# Run from the module folder: terraform init -backend=false, then terraform test.

provider "aws" {
  region                      = "us-east-1"
  access_key                  = "not-a-real-key"
  secret_key                  = "not-a-real-secret"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
}

variables {
  env                        = "dev"
  site_bucket_arn            = "arn:aws:s3:::portfolio-dev-site-123456789012"
  data_access_policy_json    = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
  parameter_read_policy_json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
  registry_arn               = "arn:aws:ecr:us-east-1:123456789012:repository/portfolio-dev-airflow"
}

run "instance_role_is_assumed_only_by_ec2" {
  command = plan

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

  assert {
    condition     = strcontains(aws_iam_role.box.assume_role_policy, "ec2.amazonaws.com")
    error_message = "Only EC2 may assume the instance role."
  }
}

run "box_can_publish_only_to_its_own_site_bucket" {
  command = plan

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

  assert {
    condition     = strcontains(aws_iam_role_policy.site_publish.policy, "portfolio-dev-site-123456789012")
    error_message = "The box must be able to publish to the dev site bucket."
  }

  assert {
    condition     = !strcontains(aws_iam_role_policy.site_publish.policy, "live")
    error_message = "A dev box must not be able to reach any live resource."
  }

  assert {
    condition     = !strcontains(aws_iam_role_policy.site_publish.policy, "s3:DeleteObject")
    error_message = "The box must not be able to delete published files."
  }
}

run "box_can_be_reached_through_session_manager_without_ssh" {
  command = plan

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

  assert {
    condition     = aws_iam_role_policy_attachment.session_manager.policy_arn == "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
    error_message = "The box must be reachable through Session Manager, so no SSH port is needed."
  }
}

run "scheduler_role_is_assumed_only_by_the_scheduler" {
  command = plan

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

  assert {
    condition     = strcontains(aws_iam_role.scheduler.assume_role_policy, "scheduler.amazonaws.com")
    error_message = "Only EventBridge Scheduler may assume the scheduler role."
  }
}

run "scheduler_can_only_start_and_stop_the_session_box" {
  command = plan

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

  assert {
    condition     = strcontains(aws_iam_role_policy.scheduler.policy, "ec2:StartInstances") && strcontains(aws_iam_role_policy.scheduler.policy, "ec2:StopInstances")
    error_message = "The scheduler must be able to start and stop the box."
  }

  assert {
    condition     = !strcontains(aws_iam_role_policy.scheduler.policy, "ec2:TerminateInstances") && !strcontains(aws_iam_role_policy.scheduler.policy, "ec2:RunInstances")
    error_message = "The scheduler must not be able to create or end instances."
  }

  assert {
    condition     = strcontains(aws_iam_role_policy.scheduler.policy, "portfolio-dev-session-box")
    error_message = "The scheduler must be limited to the session box by its name tag."
  }
}

run "refuses_a_live_site_bucket_in_a_dev_configuration" {
  command = plan

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
    site_bucket_arn = "arn:aws:s3:::portfolio-live-site-123456789012"
  }

  expect_failures = [
    aws_iam_role_policy.site_publish,
  ]
}

run "rejects_an_unknown_environment" {
  command = plan

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
    env = "staging"
  }

  expect_failures = [
    var.env,
  ]
}

run "box_can_pull_images_from_its_own_registry_but_not_push" {
  command = plan

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

  assert {
    condition     = strcontains(aws_iam_role_policy.registry_pull.policy, "ecr:BatchGetImage") && strcontains(aws_iam_role_policy.registry_pull.policy, "ecr:GetDownloadUrlForLayer")
    error_message = "The box must be able to pull images."
  }

  assert {
    condition     = !strcontains(aws_iam_role_policy.registry_pull.policy, "ecr:PutImage") && !strcontains(aws_iam_role_policy.registry_pull.policy, "ecr:InitiateLayerUpload")
    error_message = "The box must not be able to push images."
  }

  assert {
    condition     = strcontains(aws_iam_role_policy.registry_pull.policy, "repository/portfolio-dev-airflow")
    error_message = "Image pulls must be limited to this environment's repository."
  }
}

run "refuses_a_live_registry_in_a_dev_configuration" {
  command = plan

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
    registry_arn = "arn:aws:ecr:us-east-1:123456789012:repository/portfolio-live-airflow"
  }

  expect_failures = [
    aws_iam_role_policy.registry_pull,
  ]
}
