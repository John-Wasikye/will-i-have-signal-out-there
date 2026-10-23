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

# This module creates no parameters and holds no secret values. Parameter values are
# written by hand or by a pipeline at run time, never by Terraform, so they stay out of state.
# Path convention: /portfolio/<env>/<project>/<name>
#
# The module only builds the read policy. The iam module attaches it to each pipeline role.
# If a parameter uses a customer-managed KMS key, the read policy also needs kms:Decrypt on that key.
data "aws_iam_policy_document" "read" {
  statement {
    sid    = "ReadEnvironmentParameters"
    effect = "Allow"

    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:GetParametersByPath",
    ]

    resources = [
      "arn:${data.aws_partition.current.partition}:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter/portfolio/${var.env}",
      "arn:${data.aws_partition.current.partition}:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter/portfolio/${var.env}/*",
    ]
  }
}
