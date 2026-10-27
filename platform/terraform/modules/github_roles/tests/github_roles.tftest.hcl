# Plan-only tests. No AWS calls are made.
# The real provider runs so the policy documents build real JSON. Only the two lookups
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


variables {
  env              = "dev"
  site_bucket_arn  = "arn:aws:s3:::portfolio-dev-site-123456789012"
  distribution_arn = "arn:aws:cloudfront::123456789012:distribution/EDFDVBD6EXAMPLE"
  registry_arn     = "arn:aws:ecr:us-east-1:123456789012:repository/portfolio-dev-airflow"
  protected_names  = ["nfl-"]
  protected_arns   = ["arn:aws:iam::*:role/github-plan"]
}

# --- Plan role ------------------------------------------------------------------------------

run "plan_role_is_used_only_by_pull_requests_in_this_repository" {
  command = plan

  assert {
    condition     = strcontains(aws_iam_role.plan.assume_role_policy, "repo:John-Wasikye@171445038/will-i-have-signal-out-there@1412828974:pull_request")
    error_message = "The plan role must trust pull requests in this repository only."
  }

  assert {
    condition     = strcontains(aws_iam_role.plan.assume_role_policy, "sts.amazonaws.com")
    error_message = "The plan role must check the token audience."
  }

  assert {
    condition     = aws_iam_role.plan.name == "portfolio-dev-terraform-plan"
    error_message = "The plan role must be named portfolio-<env>-terraform-plan."
  }
}

run "plan_role_reads_settings_but_no_data" {
  command = plan

  assert {
    condition     = aws_iam_role_policy_attachment.plan_read_only.policy_arn == "arn:aws:iam::aws:policy/ReadOnlyAccess"
    error_message = "The plan role must use AWS's read-only policy."
  }

  assert {
    condition = alltrue([for action in ["s3:GetObject", "ssm:GetParameter", "dynamodb:Scan", "dynamodb:Query", "logs:GetLogEvents", "secretsmanager:GetSecretValue"] :
    strcontains(aws_iam_role_policy.plan_limits.policy, action)])
    error_message = "The plan role must be refused data files, parameter values, visitor records and logs."
  }
}

run "plan_role_reads_only_its_own_state" {
  command = plan

  assert {
    condition     = strcontains(aws_iam_role_policy.plan_limits.policy, "portfolio-terraform-state-123456789012/dev/*")
    error_message = "The plan role must be able to read the dev state."
  }

  assert {
    condition     = !strcontains(aws_iam_role_policy.plan_limits.policy, "s3:PutObject")
    error_message = "A plan must not write anything, not even a state lock."
  }
}

# --- Apply role -----------------------------------------------------------------------------

run "apply_role_is_used_only_by_the_approved_environment" {
  command = plan

  assert {
    condition     = strcontains(aws_iam_role.apply.assume_role_policy, "repo:John-Wasikye@171445038/will-i-have-signal-out-there@1412828974:environment:dev")
    error_message = "The apply role must trust only jobs in the dev GitHub environment."
  }

  assert {
    condition     = !strcontains(aws_iam_role.apply.assume_role_policy, "pull_request")
    error_message = "A pull request must never get the apply role."
  }
}

run "dev_apply_role_is_refused_live_and_shared_resources" {
  command = plan

  assert {
    condition = alltrue([for target in ["arn:aws:s3:::*portfolio-live-*", "arn:aws:ecs:*:*:*portfolio-live-*", "arn:aws:glue:*:*:*portfolio_live*", "portfolio-terraform-state-*/live/", "budgets:", "portfolio-dev-terraform-apply"] :
    strcontains(aws_iam_role_policy.refuse_live[0].policy, target)])
    error_message = "The dev apply role must be refused live resources, the shared budget, and changes to itself."
  }
}

# The account also runs other projects (the NFL site). Both apply roles have broad rights, so
# both are refused those projects and the OIDC provider that another project owns.
run "both_apply_roles_are_refused_other_projects_and_the_oidc_provider" {
  command = plan

  assert {
    condition = alltrue([for target in ["arn:aws:s3:::*nfl-*", "arn:aws:ecs:*:*:*nfl-*", "arn:aws:iam::*:role/*nfl-*", "arn:aws:iam::*:user/*nfl-*", "arn:aws:iam::*:policy/*nfl-*", "arn:aws:logs:*:*:*nfl-*", "arn:aws:cloudfront::*:*nfl-*", "arn:aws:iam::*:role/github-plan", "oidc-provider"] :
    strcontains(aws_iam_role_policy.refuse_other_projects.policy, target)])
    error_message = "The dev apply role must be refused the protected resources and the OIDC provider."
  }

  assert {
    condition     = aws_iam_role_policy.refuse_other_projects.role == "portfolio-dev-terraform-apply"
    error_message = "The refusal must be attached to the apply role."
  }
}

run "live_apply_role_has_no_refusal_list" {
  command = plan

  variables {
    env              = "live"
    site_bucket_arn  = "arn:aws:s3:::portfolio-live-site-123456789012"
    registry_arn     = "arn:aws:ecr:us-east-1:123456789012:repository/portfolio-live-airflow"
    distribution_arn = "arn:aws:cloudfront::123456789012:distribution/EDFDVBD6EXAMPLE"
  }

  assert {
    condition     = length(aws_iam_role_policy.refuse_live) == 0
    error_message = "Live owns the shared resources, so its apply role is not refused them."
  }

  assert {
    condition     = strcontains(aws_iam_role_policy.refuse_other_projects.policy, "arn:aws:s3:::*nfl-*") && strcontains(aws_iam_role_policy.refuse_other_projects.policy, "oidc-provider")
    error_message = "The live apply role must also be refused other projects and the OIDC provider."
  }

  assert {
    condition     = strcontains(aws_iam_role.apply.assume_role_policy, "environment:live")
    error_message = "The live apply role must trust only jobs in the live GitHub environment."
  }
}

# --- Deploy role ----------------------------------------------------------------------------

run "deploy_role_is_used_only_by_the_approved_environment" {
  command = plan

  assert {
    condition     = strcontains(aws_iam_role.deploy.assume_role_policy, "repo:John-Wasikye@171445038/will-i-have-signal-out-there@1412828974:environment:dev")
    error_message = "The deploy role must trust only jobs in the dev GitHub environment."
  }
}

run "deploy_role_uploads_the_site_but_never_the_published_data" {
  command = plan

  assert {
    condition     = strcontains(aws_iam_role_policy.deploy.policy, "portfolio-dev-site-123456789012/*") && strcontains(aws_iam_role_policy.deploy.policy, "s3:PutObject")
    error_message = "The deploy role must be able to upload the site."
  }

  assert {
    condition     = strcontains(aws_iam_role_policy.deploy.policy, "portfolio-dev-site-123456789012/published/*") && strcontains(aws_iam_role_policy.deploy.policy, "portfolio-dev-site-123456789012/status.json")
    error_message = "The deploy role must be refused the published files and status.json, which the box owns."
  }

  assert {
    condition     = strcontains(aws_iam_role_policy.deploy.policy, "cloudfront:CreateInvalidation") && strcontains(aws_iam_role_policy.deploy.policy, "distribution/EDFDVBD6EXAMPLE")
    error_message = "The deploy role must be able to clear this distribution's cache."
  }

  assert {
    condition     = strcontains(aws_iam_role_policy.deploy.policy, "ecr:PutImage") && strcontains(aws_iam_role_policy.deploy.policy, "repository/portfolio-dev-airflow")
    error_message = "The deploy role must be able to push to this environment's image repository."
  }

  assert {
    condition     = !strcontains(aws_iam_role_policy.deploy.policy, "ecr:DeleteRepository") && !strcontains(aws_iam_role_policy.deploy.policy, "s3:DeleteBucket")
    error_message = "The deploy role must not be able to remove the repository or the bucket."
  }
}

run "refuses_a_live_site_bucket_in_a_dev_configuration" {
  command = plan

  variables {
    site_bucket_arn = "arn:aws:s3:::portfolio-live-site-123456789012"
  }

  expect_failures = [
    aws_iam_role_policy.deploy,
  ]
}

run "refuses_a_live_registry_in_a_dev_configuration" {
  command = plan

  variables {
    registry_arn = "arn:aws:ecr:us-east-1:123456789012:repository/portfolio-live-airflow"
  }

  expect_failures = [
    aws_iam_role_policy.deploy,
  ]
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

# IAM refuses a policy whose ARN has a wildcard for the service (arn:aws:*:...). The first live
# apply failed on exactly that, so every refusal names its services.
run "no_refusal_uses_a_wildcard_service" {
  command = plan

  assert {
    condition     = !strcontains(aws_iam_role_policy.refuse_live[0].policy, "arn:aws:*:") && !strcontains(aws_iam_role_policy.refuse_other_projects.policy, "arn:aws:*:")
    error_message = "IAM refuses an ARN whose service is a wildcard, so every refused ARN must name its service."
  }
}

# IAM also refuses an IAM ARN whose resource part does not start with a type such as role/ or
# user/. The second live apply failed on arn:aws:iam::*:*nfl-*, so IAM names are refused by type.
run "no_refusal_uses_an_iam_arn_without_a_resource_type" {
  command = plan

  assert {
    condition     = length(regexall("arn:aws:iam::[^:]*:[*]", aws_iam_role_policy.refuse_live[0].policy)) == 0 && length(regexall("arn:aws:iam::[^:]*:[*]", aws_iam_role_policy.refuse_other_projects.policy)) == 0
    error_message = "IAM refuses an IAM ARN whose resource part starts with a wildcard, so each one must name its type, such as role/."
  }

  assert {
    condition     = strcontains(aws_iam_role_policy.refuse_live[0].policy, "arn:aws:iam::*:role/*portfolio-live-*")
    error_message = "The dev apply role must still be refused the live roles."
  }
}

run "rejects_a_protected_arn_with_a_wildcard_service" {
  command = plan

  variables {
    protected_arns = ["arn:aws:*:*:*:*nfl-*"]
  }

  expect_failures = [
    var.protected_arns,
  ]
}
# GitHub signs this repository's tokens with its permanent owner and repository IDs
# (repo:owner@id/name@id:...). A trust written with the plain owner/name never matches, and the
# first deploy failed on exactly that, so the plain form is refused.
run "rejects_a_repository_without_its_ids" {
  command = plan

  variables {
    github_repo = "John-Wasikye/will-i-have-signal-out-there"
  }

  expect_failures = [
    var.github_repo,
  ]
}
