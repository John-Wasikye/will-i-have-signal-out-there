# Plan-only tests. No AWS calls are made.
# The real provider runs, so aws_iam_policy_document builds real JSON. Only the three
# lookups that need an AWS account are overridden with fixed values.
# Run from the module folder: terraform init -backend=false, then terraform test.

provider "aws" {
  region                      = "us-east-1"
  access_key                  = "not-a-real-key"
  secret_key                  = "not-a-real-secret"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
}

run "dev_policy_references_only_dev_buckets" {
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
    env                        = "dev"
    raw_bucket_arn             = "arn:aws:s3:::portfolio-dev-raw-123456789012"
    lake_bucket_arn            = "arn:aws:s3:::portfolio-dev-lake-123456789012"
    glue_database_name         = "portfolio_dev"
    parameter_read_policy_json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    create_oidc_provider       = false
  }

  assert {
    condition     = !strcontains(aws_iam_role_policy.data_access["platform_skeleton"].policy, "live")
    error_message = "A dev pipeline role must not reference any live resource."
  }
}

run "dev_role_trusts_any_ref_in_the_repository" {
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
    env                        = "dev"
    raw_bucket_arn             = "arn:aws:s3:::portfolio-dev-raw-123456789012"
    lake_bucket_arn            = "arn:aws:s3:::portfolio-dev-lake-123456789012"
    glue_database_name         = "portfolio_dev"
    parameter_read_policy_json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    create_oidc_provider       = false
  }

  assert {
    condition     = strcontains(aws_iam_role.pipeline["platform_skeleton"].assume_role_policy, "repo:John-Wasikye/will-i-have-signal-out-there:*")
    error_message = "Dev roles must trust any ref in the repository."
  }
}

run "live_role_trusts_only_the_main_branch" {
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
    env                        = "live"
    raw_bucket_arn             = "arn:aws:s3:::portfolio-live-raw-123456789012"
    lake_bucket_arn            = "arn:aws:s3:::portfolio-live-lake-123456789012"
    glue_database_name         = "portfolio_live"
    parameter_read_policy_json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
  }

  assert {
    condition     = output.github_subject == "repo:John-Wasikye/will-i-have-signal-out-there:ref:refs/heads/main"
    error_message = "Live roles must trust only the main branch."
  }
}

run "refuses_a_live_bucket_in_a_dev_configuration" {
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
    env                        = "dev"
    raw_bucket_arn             = "arn:aws:s3:::portfolio-live-raw-123456789012"
    lake_bucket_arn            = "arn:aws:s3:::portfolio-dev-lake-123456789012"
    glue_database_name         = "portfolio_dev"
    parameter_read_policy_json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    create_oidc_provider       = false
  }

  expect_failures = [
    aws_iam_role_policy.data_access,
  ]
}

run "refuses_a_live_glue_database_in_a_dev_configuration" {
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
    env                        = "dev"
    raw_bucket_arn             = "arn:aws:s3:::portfolio-dev-raw-123456789012"
    lake_bucket_arn            = "arn:aws:s3:::portfolio-dev-lake-123456789012"
    glue_database_name         = "portfolio_live"
    parameter_read_policy_json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    create_oidc_provider       = false
  }

  expect_failures = [
    aws_iam_role_policy.data_access,
  ]
}

run "rejects_a_pipeline_name_with_capitals" {
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
    env                        = "dev"
    pipeline_names             = ["Platform-Skeleton"]
    raw_bucket_arn             = "arn:aws:s3:::portfolio-dev-raw-123456789012"
    lake_bucket_arn            = "arn:aws:s3:::portfolio-dev-lake-123456789012"
    glue_database_name         = "portfolio_dev"
    parameter_read_policy_json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    create_oidc_provider       = false
  }

  expect_failures = [
    var.pipeline_names,
  ]
}

run "exposes_the_data_access_policy_for_reuse" {
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
    env                        = "dev"
    raw_bucket_arn             = "arn:aws:s3:::portfolio-dev-raw-123456789012"
    lake_bucket_arn            = "arn:aws:s3:::portfolio-dev-lake-123456789012"
    glue_database_name         = "portfolio_dev"
    parameter_read_policy_json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    create_oidc_provider       = false
  }

  assert {
    condition     = strcontains(output.data_access_policy_json, "portfolio-dev-raw-123456789012")
    error_message = "The exposed policy must cover this environment's raw bucket."
  }

  assert {
    condition     = !strcontains(output.data_access_policy_json, "live")
    error_message = "A dev policy must not mention any live resource."
  }
}
