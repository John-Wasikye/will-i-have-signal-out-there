terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id

  # One entry per bucket. The account ID in the name keeps bucket names globally unique.
  # Object Lock is set only on the live raw bucket, and it must be set when the bucket is created.
  # The 14-day dev expiry applies to dev raw and lake data only, not to the site bucket.
  buckets = {
    raw = {
      name        = "portfolio-${var.env}-raw-${local.account_id}"
      object_lock = var.env == "live"
      dev_expiry  = var.env == "dev"
    }
    lake = {
      name        = "portfolio-${var.env}-lake-${local.account_id}"
      object_lock = false
      dev_expiry  = var.env == "dev"
    }
    site = {
      name        = "portfolio-${var.env}-site-${local.account_id}"
      object_lock = false
      dev_expiry  = false
    }
  }

  # Built from the names, which are known before the buckets exist. This lets a plan show
  # the full bucket policies, so the tests can check them.
  bucket_arns = {
    for key, bucket in local.buckets :
    key => "arn:${data.aws_partition.current.partition}:s3:::${bucket.name}"
  }
}

resource "aws_s3_bucket" "this" {
  for_each = local.buckets

  bucket              = each.value.name
  object_lock_enabled = each.value.object_lock

  # Dev buckets can be emptied on destroy so teardown stays cheap. Live buckets never are.
  force_destroy = var.env == "dev"
}

resource "aws_s3_bucket_versioning" "this" {
  for_each = local.buckets

  bucket = aws_s3_bucket.this[each.key].id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = local.buckets

  bucket = aws_s3_bucket.this[each.key].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each = local.buckets

  bucket = aws_s3_bucket.this[each.key].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# A bucket has only one policy, so every rule for a bucket goes in this document.
data "aws_iam_policy_document" "bucket" {
  for_each = local.buckets

  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [local.bucket_arns[each.key], "${local.bucket_arns[each.key]}/*"]

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

  # Only the site bucket can be read through CloudFront, and only by the one distribution
  # that serves the site.
  dynamic "statement" {
    for_each = each.key == "site" && var.site_distribution_arn != null ? [1] : []

    content {
      sid       = "AllowCloudFrontToRead"
      effect    = "Allow"
      actions   = ["s3:GetObject"]
      resources = ["${local.bucket_arns[each.key]}/*"]

      principals {
        type        = "Service"
        identifiers = ["cloudfront.amazonaws.com"]
      }

      condition {
        test     = "StringEquals"
        variable = "aws:SourceArn"
        values   = [var.site_distribution_arn]
      }
    }
  }
}

resource "aws_s3_bucket_policy" "this" {
  for_each = local.buckets

  bucket = aws_s3_bucket.this[each.key].id
  policy = data.aws_iam_policy_document.bucket[each.key].json

  depends_on = [aws_s3_bucket_public_access_block.this]
}

# Live raw files cannot be deleted or overwritten for 30 days (ADR-0019).
# Governance mode lets an administrator with a special permission override it.
resource "aws_s3_bucket_object_lock_configuration" "raw_live" {
  for_each = { for key, bucket in local.buckets : key => bucket if bucket.object_lock }

  bucket = aws_s3_bucket.this[each.key].id

  rule {
    default_retention {
      mode = "GOVERNANCE"
      days = 30
    }
  }

  depends_on = [aws_s3_bucket_versioning.this]
}

# Clean-up rules (requirements PR-20, ADR-0019). Prefixes "tmp/", "checkpoints/" and "logs/" are
# the only places pipelines write temporary data, checkpoints and logs.
# Raw and published data are kept, except for the 14-day dev expiry.
resource "aws_s3_bucket_lifecycle_configuration" "this" {
  for_each = local.buckets

  bucket = aws_s3_bucket.this[each.key].id

  depends_on = [aws_s3_bucket_versioning.this]

  rule {
    id     = "abort-failed-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  rule {
    id     = "old-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }

  rule {
    id     = "temporary-files"
    status = "Enabled"

    filter {
      prefix = "tmp/"
    }

    expiration {
      days = 7
    }
  }

  rule {
    id     = "spark-checkpoints"
    status = "Enabled"

    filter {
      prefix = "checkpoints/"
    }

    expiration {
      days = 7
    }
  }

  rule {
    id     = "pipeline-logs"
    status = "Enabled"

    filter {
      prefix = "logs/"
    }

    expiration {
      days = 90
    }
  }

  dynamic "rule" {
    for_each = each.value.dev_expiry ? [1] : []

    content {
      id     = "dev-data-14-days"
      status = "Enabled"

      filter {}

      expiration {
        days = 14
      }
    }
  }
}

# Optional size alarm. S3 publishes BucketSizeBytes once a day, so the alarm evaluates daily.
# The alarm has no notification target unless alarm_actions is set.
resource "aws_cloudwatch_metric_alarm" "bucket_size" {
  for_each = local.buckets

  alarm_name          = "${each.value.name}-size"
  alarm_description   = "Storage in ${each.value.name} is above the size limit set for the portfolio platform."
  namespace           = "AWS/S3"
  metric_name         = "BucketSizeBytes"
  statistic           = "Average"
  period              = 86400
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.size_alarm_bytes
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions

  dimensions = {
    BucketName  = aws_s3_bucket.this[each.key].id
    StorageType = "StandardStorage"
  }
}
