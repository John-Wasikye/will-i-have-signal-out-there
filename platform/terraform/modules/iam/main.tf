terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

data "aws_partition" "current" {}

data "aws_region" "current" {}

data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
  region     = data.aws_region.current.name

  github_host = "token.actions.githubusercontent.com"

  # The provider ARN is built from the account ID so that dev can trust a provider that live created.
  oidc_provider_arn = var.create_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : "arn:${local.partition}:iam::${local.account_id}:oidc-provider/${local.github_host}"

  glue_catalog_arn  = "arn:${local.partition}:glue:${local.region}:${local.account_id}:catalog"
  glue_database_arn = "arn:${local.partition}:glue:${local.region}:${local.account_id}:database/${var.glue_database_name}"
  glue_tables_arn   = "arn:${local.partition}:glue:${local.region}:${local.account_id}:table/${var.glue_database_name}/*"

  # A job that names a GitHub environment gets ...:environment:<name> as its token subject, and
  # only after that environment's rules (my approval, main branch only) have let it run. Trusting
  # the main branch alone would let any workflow pushed to main use the role without asking me.
  github_subject = "repo:${var.github_repo}:environment:${var.env}"
}

# GitHub OIDC provider. One per AWS account, so at most one configuration creates it. In
# John's account the NFL project's Terraform already owns it, so both envs/ set
# create_oidc_provider to false and trust it by its ARN.
resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 1 : 0

  url            = "https://${local.github_host}"
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_policy_document" "trust" {
  statement {
    sid     = "GitHubActionsOIDC"
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
      values   = [local.github_subject]
    }
  }
}

resource "aws_iam_role" "pipeline" {
  for_each = toset(var.pipeline_names)

  name               = "portfolio-${var.env}-${each.key}"
  description        = "Pipeline role for ${each.key} in the ${var.env} environment. Assumed by GitHub Actions through OIDC."
  assume_role_policy = data.aws_iam_policy_document.trust.json
}

# Data access for every pipeline role in this environment. Each resource is scoped to this
# environment's buckets and Glue database. Dev policies reference only dev ARNs.
data "aws_iam_policy_document" "data_access" {
  statement {
    sid       = "ListDataBuckets"
    effect    = "Allow"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [var.raw_bucket_arn, var.lake_bucket_arn]
  }

  # Raw files are read and added, never deleted by a pipeline. Object Lock and the clean-up rules handle removal.
  statement {
    sid    = "RawFiles"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:PutObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${var.raw_bucket_arn}/*"]
  }

  # Lake files need delete, because Iceberg maintenance removes orphan files and old snapshots.
  statement {
    sid    = "LakeFiles"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${var.lake_bucket_arn}/*"]
  }

  statement {
    sid       = "GlueCatalogAndDatabase"
    effect    = "Allow"
    actions   = ["glue:GetDatabase", "glue:GetDatabases"]
    resources = [local.glue_catalog_arn, local.glue_database_arn]
  }

  statement {
    sid    = "GlueTables"
    effect = "Allow"
    actions = [
      "glue:GetTable",
      "glue:GetTables",
      "glue:GetTableVersion",
      "glue:GetTableVersions",
      "glue:CreateTable",
      "glue:UpdateTable",
      "glue:DeleteTable",
      "glue:GetPartition",
      "glue:GetPartitions",
      "glue:BatchGetPartition",
      "glue:CreatePartition",
      "glue:BatchCreatePartition",
      "glue:UpdatePartition",
      "glue:DeletePartition",
      "glue:BatchDeletePartition",
    ]
    resources = [local.glue_catalog_arn, local.glue_database_arn, local.glue_tables_arn]
  }
}

resource "aws_iam_role_policy" "data_access" {
  for_each = aws_iam_role.pipeline

  name   = "data-access"
  role   = each.value.id
  policy = data.aws_iam_policy_document.data_access.json

  lifecycle {
    # Guards against passing a dev role the live bucket ARNs, or the reverse.
    precondition {
      condition     = strcontains(var.raw_bucket_arn, "portfolio-${var.env}-raw-") && strcontains(var.lake_bucket_arn, "portfolio-${var.env}-lake-")
      error_message = "The bucket ARNs must belong to the same environment as the env variable."
    }

    precondition {
      condition     = startswith(var.glue_database_name, "portfolio_${var.env}")
      error_message = "The Glue database must belong to the same environment as the env variable."
    }
  }
}

# Parameter Store read access, built by the parameters module for /portfolio/<env>/*.
resource "aws_iam_role_policy" "parameters" {
  for_each = aws_iam_role.pipeline

  name   = "parameter-store-read"
  role   = each.value.id
  policy = var.parameter_read_policy_json
}
