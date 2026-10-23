data "aws_partition" "current" {}

data "aws_region" "current" {}

data "aws_caller_identity" "current" {}

locals {
  partition  = data.aws_partition.current.partition
  account_id = data.aws_caller_identity.current.account_id

  # The live- prefix puts the trail and its bucket on the dev apply role's refusal list.
  trail_name  = "portfolio-live-audit"
  bucket_name = "portfolio-live-audit-${local.account_id}"

  # Built from their parts, so the bucket policy is known at plan time and can name the trail
  # before it exists.
  bucket_arn = "arn:${local.partition}:s3:::${local.bucket_name}"
  trail_arn  = "arn:${local.partition}:cloudtrail:${data.aws_region.current.name}:${local.account_id}:trail/${local.trail_name}"
}

# --- The log bucket -------------------------------------------------------------------------

# The security logs outlive any stack, so a destroy refuses to delete a bucket that holds them.
resource "aws_s3_bucket" "audit" {
  bucket        = local.bucket_name
  force_destroy = false
}

resource "aws_s3_bucket_versioning" "audit" {
  bucket = aws_s3_bucket.audit.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "audit" {
  bucket = aws_s3_bucket.audit.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# CloudTrail checks the bucket's ACL, then writes under AWSLogs/<account>/. Both are allowed
# for this trail only, so no other trail or account can fill the bucket.
data "aws_iam_policy_document" "audit" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [local.bucket_arn, "${local.bucket_arn}/*"]

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

  statement {
    sid       = "TrailChecksTheBucket"
    effect    = "Allow"
    actions   = ["s3:GetBucketAcl"]
    resources = [local.bucket_arn]

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceArn"
      values   = [local.trail_arn]
    }
  }

  statement {
    sid       = "TrailWritesLogs"
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${local.bucket_arn}/AWSLogs/${local.account_id}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceArn"
      values   = [local.trail_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }
  }
}

resource "aws_s3_bucket_policy" "audit" {
  bucket = aws_s3_bucket.audit.id
  policy = data.aws_iam_policy_document.audit.json

  depends_on = [aws_s3_bucket_public_access_block.audit]
}

# Clean-up rules (requirements PR-20, ADR-0019): security logs are kept one year.
resource "aws_s3_bucket_lifecycle_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id

  depends_on = [aws_s3_bucket_versioning.audit]

  rule {
    id     = "security-logs-one-year"
    status = "Enabled"

    filter {}

    expiration {
      days = 365
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
    id     = "abort-failed-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# S3 publishes BucketSizeBytes once a day, so the alarm evaluates daily.
resource "aws_cloudwatch_metric_alarm" "bucket_size" {
  alarm_name          = "${local.bucket_name}-size"
  alarm_description   = "Storage in ${local.bucket_name} is above the size limit set for the security logs."
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
    BucketName  = local.bucket_name
    StorageType = "StandardStorage"
  }
}

# --- The trail ------------------------------------------------------------------------------

# One trail for the whole account, so envs/live is the only caller. Management events cover
# every change to the account and every read of a key, Parameter Store reads included. The
# first trail's management events are free. Data events (each S3 object read) are billed per
# event, so they are not recorded.
resource "aws_cloudtrail" "audit" {
  name                          = local.trail_name
  s3_bucket_name                = aws_s3_bucket.audit.id
  is_multi_region_trail         = true
  include_global_service_events = true
  enable_log_file_validation    = true

  event_selector {
    read_write_type           = "All"
    include_management_events = true
  }

  depends_on = [aws_s3_bucket_policy.audit]
}
