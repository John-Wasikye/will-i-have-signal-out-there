data "aws_partition" "current" {}

data "aws_caller_identity" "current" {}

locals {
  partition  = data.aws_partition.current.partition
  account_id = data.aws_caller_identity.current.account_id

  github_host = "token.actions.githubusercontent.com"
  # The account has one provider, owned by the NFL project's Terraform. Building its ARN lets
  # these roles trust it without managing it.
  oidc_provider_arn = "arn:${local.partition}:iam::${local.account_id}:oidc-provider/${local.github_host}"

  # GitHub puts the event in the token subject. A pull request job gets ...:pull_request. A job
  # that names a GitHub environment gets ...:environment:<name>, and only after that
  # environment's rules (required reviewer, allowed branches) have let it run.
  plan_subject   = "repo:${var.github_repo}:pull_request"
  gated_subject  = "repo:${var.github_repo}:environment:${var.env}"
  apply_role     = "portfolio-${var.env}-terraform-apply"
  state_bucket   = "arn:${local.partition}:s3:::portfolio-terraform-state-${local.account_id}"
  own_state_path = "${local.state_bucket}/${var.env}/*"

  # IAM refuses an ARN whose service is a wildcard, so a "refuse anything named X" rule is
  # written once per service. These are the services the projects in this account use.
  # S3 ARNs have no region or account, and IAM and CloudFront have no region.
  named_resource_arns = {
    for name in distinct(concat(["portfolio-live-", "portfolio_live"], var.protected_names)) : name => concat(
      ["arn:${local.partition}:s3:::*${name}*"],
      [for service in ["iam", "cloudfront"] : "arn:${local.partition}:${service}::*:*${name}*"],
      [for service in local.regional_services : "arn:${local.partition}:${service}:*:*:*${name}*"],
    )
  }
  regional_services = [
    "apigateway", "cloudtrail", "cloudwatch", "dynamodb", "ec2", "ecr", "ecs", "events", "glue",
    "kms", "lambda", "logs", "scheduler", "secretsmanager", "sns", "sqs", "ssm", "states",
  ]
}

data "aws_iam_policy_document" "plan_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.github_host}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.github_host}:sub"
      values   = [local.plan_subject]
    }
  }
}

data "aws_iam_policy_document" "gated_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.github_host}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.github_host}:sub"
      values   = [local.gated_subject]
    }
  }
}

# --- Plan role: any pull request, read-only -------------------------------------------------

resource "aws_iam_role" "plan" {
  name               = "portfolio-${var.env}-terraform-plan"
  description        = "Runs terraform plan for ${var.env} on pull requests. Reads settings, never data."
  assume_role_policy = data.aws_iam_policy_document.plan_trust.json
}

# A plan refreshes every resource, so it needs to read the settings of everything Terraform
# manages. AWS's read-only policy covers that, and the limits below take the data back out.
resource "aws_iam_role_policy_attachment" "plan_read_only" {
  role       = aws_iam_role.plan.name
  policy_arn = "arn:${local.partition}:iam::aws:policy/ReadOnlyAccess"
}

data "aws_iam_policy_document" "plan_limits" {
  statement {
    sid       = "ReadOwnState"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = [local.own_state_path]
  }

  statement {
    sid       = "ListStateBucket"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [local.state_bucket]
  }

  # The state key is created by the bootstrap and has no fixed ARN here, so it is found by alias.
  statement {
    sid       = "DecryptState"
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
    resources = ["*"]

    condition {
      test     = "ForAnyValue:StringEquals"
      variable = "kms:ResourceAliases"
      values   = ["alias/portfolio-terraform-state"]
    }
  }

  # Pull requests can come from any branch, so this role must not see what the platform holds:
  # data files, parameter values, visitor records or logs. The plan never needs them.
  statement {
    sid           = "NoDataFiles"
    effect        = "Deny"
    actions       = ["s3:GetObject", "s3:GetObjectVersion"]
    not_resources = [local.own_state_path]
  }

  statement {
    sid    = "NoDataRecords"
    effect = "Deny"
    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:GetParametersByPath",
      "ssm:GetParameterHistory",
      "secretsmanager:GetSecretValue",
      "dynamodb:GetItem",
      "dynamodb:BatchGetItem",
      "dynamodb:Query",
      "dynamodb:Scan",
      "logs:GetLogEvents",
      "logs:FilterLogEvents",
      "logs:StartQuery",
      "logs:GetQueryResults",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "plan_limits" {
  name   = "state-and-no-data"
  role   = aws_iam_role.plan.id
  policy = data.aws_iam_policy_document.plan_limits.json
}

# --- Apply role: only after the GitHub environment lets the job run -------------------------

resource "aws_iam_role" "apply" {
  name               = local.apply_role
  description        = "Runs terraform apply for ${var.env}, only from the ${var.env} GitHub environment."
  assume_role_policy = data.aws_iam_policy_document.gated_trust.json
}

# Terraform creates roles, functions, buckets and the rest, so apply needs broad rights. The
# GitHub environment is the guard: it decides who approves and which branch may run it.
resource "aws_iam_role_policy_attachment" "apply_admin" {
  role       = aws_iam_role.apply.name
  policy_arn = "arn:${local.partition}:iam::aws:policy/AdministratorAccess"
}

# Dev and live share one account, so the dev apply role is refused everything live, the
# budget that envs/live owns, and changes to itself. That last one means a change
# to this role in dev is applied by hand, from my own machine.
data "aws_iam_policy_document" "refuse_live" {
  statement {
    sid     = "RefuseLiveResources"
    effect  = "Deny"
    actions = ["*"]
    resources = concat(
      local.named_resource_arns["portfolio-live-"],
      local.named_resource_arns["portfolio_live"],
      ["arn:${local.partition}:s3:::portfolio-terraform-state-*/live/*"],
    )
  }

  statement {
    sid     = "RefuseSharedResources"
    effect  = "Deny"
    actions = ["budgets:*"]
    resources = [
      "*",
    ]
  }


  statement {
    sid       = "RefuseChangesToItself"
    effect    = "Deny"
    actions   = ["iam:*"]
    resources = ["arn:${local.partition}:iam::${local.account_id}:role/${local.apply_role}"]
  }
}

resource "aws_iam_role_policy" "refuse_live" {
  count = var.env == "dev" ? 1 : 0

  name   = "refuse-live"
  role   = aws_iam_role.apply.id
  policy = data.aws_iam_policy_document.refuse_live.json
}
# The account also runs other projects, such as the NFL site, and AdministratorAccess would
# reach them. Both apply roles are refused them, and the GitHub OIDC provider, which another
# project's Terraform owns and every project's roles trust.
data "aws_iam_policy_document" "refuse_other_projects" {
  dynamic "statement" {
    for_each = length(var.protected_names) + length(var.protected_arns) > 0 ? [1] : []

    content {
      sid     = "RefuseOtherProjects"
      effect  = "Deny"
      actions = ["*"]
      resources = concat(
        flatten([for name in var.protected_names : local.named_resource_arns[name]]),
        var.protected_arns,
      )
    }
  }

  statement {
    sid    = "RefuseTheOidcProvider"
    effect = "Deny"
    actions = [
      "iam:CreateOpenIDConnectProvider",
      "iam:DeleteOpenIDConnectProvider",
      "iam:UpdateOpenIDConnectProviderThumbprint",
      "iam:AddClientIDToOpenIDConnectProvider",
      "iam:RemoveClientIDFromOpenIDConnectProvider",
      "iam:TagOpenIDConnectProvider",
      "iam:UntagOpenIDConnectProvider",
    ]
    resources = ["arn:${local.partition}:iam::${local.account_id}:oidc-provider/*"]
  }
}

resource "aws_iam_role_policy" "refuse_other_projects" {
  name   = "refuse-other-projects"
  role   = aws_iam_role.apply.name
  policy = data.aws_iam_policy_document.refuse_other_projects.json
}

# --- Deploy role: site files and the Airflow image ------------------------------------------

resource "aws_iam_role" "deploy" {
  name               = "portfolio-${var.env}-deploy"
  description        = "Uploads the site and pushes the Airflow image for ${var.env}, only from the ${var.env} GitHub environment."
  assume_role_policy = data.aws_iam_policy_document.gated_trust.json
}

data "aws_iam_policy_document" "deploy" {
  statement {
    sid       = "ListSiteBucket"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [var.site_bucket_arn]
  }

  # The upload replaces the old site, so it deletes files that the new build no longer has.
  statement {
    sid       = "UploadSite"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${var.site_bucket_arn}/*"]
  }

  # The box writes the published data and status.json. A site upload must never touch them.
  statement {
    sid     = "LeaveTheBoxFilesAlone"
    effect  = "Deny"
    actions = ["s3:PutObject", "s3:DeleteObject"]
    resources = [
      "${var.site_bucket_arn}/published/*",
      "${var.site_bucket_arn}/status.json",
    ]
  }

  statement {
    sid       = "ClearTheCache"
    effect    = "Allow"
    actions   = ["cloudfront:CreateInvalidation", "cloudfront:GetInvalidation"]
    resources = [var.distribution_arn]
  }

  # The registry token cannot be limited to one repository.
  statement {
    sid       = "GetRegistryToken"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid    = "PushTheImage"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:DescribeImages",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [var.registry_arn]
  }
}

resource "aws_iam_role_policy" "deploy" {
  name   = "site-and-image"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json

  lifecycle {
    # Guards against giving the dev deploy role a live bucket or repository, or the reverse.
    precondition {
      condition     = strcontains(var.site_bucket_arn, "portfolio-${var.env}-site-")
      error_message = "The site bucket ARN must belong to the same environment as the env variable."
    }

    precondition {
      condition     = endswith(var.registry_arn, "repository/portfolio-${var.env}-airflow")
      error_message = "The repository ARN must belong to the same environment as the env variable."
    }
  }
}
