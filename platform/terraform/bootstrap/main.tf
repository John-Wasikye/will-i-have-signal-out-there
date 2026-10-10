# Bootstrap: creates the bucket that holds Terraform state for dev and live.
#
# This is a separate root configuration. It is applied once, by hand, from John's
# machine, before envs/dev or envs/live are initialised. It is not run by CI.
#
# Its own state is local. Keep that file outside the repository, for example by
# running: terraform apply -state=C:\Users\johnw\secure\portfolio-bootstrap.tfstate
# The .gitignore blocks *.tfstate as a backstop only.
#
# This configuration never creates AWS resources in the environment folders.

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "will-i-have-signal-out-there"
      Environment = "shared"
      ManagedBy   = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "state_kms" {
  # The default key policy: the account root may use the key through IAM policies.
  statement {
    sid       = "AccountRootAdmin"
    actions   = ["kms:*"]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }
}

resource "aws_kms_key" "state" {
  description             = "Customer-managed key for the portfolio Terraform state bucket"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy                  = data.aws_iam_policy_document.state_kms.json

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_kms_alias" "state" {
  name          = "alias/portfolio-terraform-state"
  target_key_id = aws_kms_key.state.key_id
}

resource "aws_s3_bucket" "state" {
  bucket = "portfolio-terraform-state-${data.aws_caller_identity.current.account_id}"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.state.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket = aws_s3_bucket.state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_iam_policy_document" "state_tls_only" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = data.aws_iam_policy_document.state_tls_only.json

  depends_on = [aws_s3_bucket_public_access_block.state]
}
