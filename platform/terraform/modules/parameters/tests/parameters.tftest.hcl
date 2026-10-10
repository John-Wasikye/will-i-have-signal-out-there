# Plan-only tests. No AWS calls are made.
# The real provider runs so the policy document builds real JSON. Only the three lookups
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

run "dev_policy_covers_only_the_dev_path" {
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
    env = "dev"
  }

  assert {
    condition     = strcontains(output.read_policy_json, "parameter/portfolio/dev/*")
    error_message = "The policy must allow reading everything under /portfolio/dev/."
  }

  assert {
    condition     = !strcontains(output.read_policy_json, "parameter/portfolio/live")
    error_message = "The dev policy must not allow reading live parameters."
  }
}

run "policy_is_read_only" {
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
    env = "live"
  }

  assert {
    condition     = !strcontains(output.read_policy_json, "ssm:PutParameter") && !strcontains(output.read_policy_json, "ssm:DeleteParameter")
    error_message = "The parameter policy must not allow writing or deleting parameters."
  }
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
