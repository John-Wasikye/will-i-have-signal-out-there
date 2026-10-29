# Plan-only tests. No AWS calls are made.
# The real provider runs so the bucket policy builds real JSON. Only the three lookups that
# need an AWS account are overridden with fixed values, for every run in this file.
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

override_data {
  target = data.aws_region.current
  values = {
    name = "us-east-1"
  }
}

run "the_trail_covers_every_region_and_the_global_services" {
  command = plan

  assert {
    condition     = aws_cloudtrail.audit.is_multi_region_trail && aws_cloudtrail.audit.include_global_service_events
    error_message = "The trail must log every region and global services such as IAM."
  }

  assert {
    condition     = aws_cloudtrail.audit.enable_log_file_validation
    error_message = "Log files must carry digests, so a changed or deleted log can be detected."
  }
}

run "the_trail_records_reads_so_every_parameter_store_read_is_logged" {
  command = plan

  assert {
    condition     = one(aws_cloudtrail.audit.event_selector).read_write_type == "All" && one(aws_cloudtrail.audit.event_selector).include_management_events
    error_message = "The trail must record read events as well as writes (security-and-privacy.md: every read of a key is logged)."
  }
}

run "security_logs_are_kept_one_year" {
  command = plan

  assert {
    condition     = one([for rule in aws_s3_bucket_lifecycle_configuration.audit.rule : rule.expiration[0].days if rule.id == "security-logs-one-year"]) == 365
    error_message = "Security logs must be kept for one year and then removed (PR-20)."
  }

  assert {
    condition     = one([for rule in aws_s3_bucket_lifecycle_configuration.audit.rule : rule.noncurrent_version_expiration[0].noncurrent_days if rule.id == "old-versions"]) == 30
    error_message = "Old versions must be removed after 30 days (PR-20)."
  }

  assert {
    condition     = one([for rule in aws_s3_bucket_lifecycle_configuration.audit.rule : rule.abort_incomplete_multipart_upload[0].days_after_initiation if rule.id == "abort-failed-uploads"]) == 7
    error_message = "Failed uploads must be cleaned up after 7 days (PR-20)."
  }
}

run "the_log_bucket_is_private_encrypted_and_versioned" {
  command = plan

  assert {
    condition     = aws_s3_bucket.audit.bucket == "portfolio-live-audit-123456789012"
    error_message = "The bucket name must start with portfolio-live-, so the dev apply role is refused it."
  }

  assert {
    condition     = aws_s3_bucket_public_access_block.audit.block_public_acls && aws_s3_bucket_public_access_block.audit.block_public_policy && aws_s3_bucket_public_access_block.audit.ignore_public_acls && aws_s3_bucket_public_access_block.audit.restrict_public_buckets
    error_message = "The log bucket must block every kind of public access."
  }

  assert {
    condition     = aws_s3_bucket_versioning.audit.versioning_configuration[0].status == "Enabled"
    error_message = "The log bucket must keep versions, so an overwritten log can be recovered."
  }

  assert {
    condition     = one(aws_s3_bucket_server_side_encryption_configuration.audit.rule).apply_server_side_encryption_by_default[0].sse_algorithm == "AES256"
    error_message = "The logs must be encrypted at rest."
  }

  assert {
    condition     = aws_s3_bucket.audit.force_destroy == false
    error_message = "A destroy must never delete the security logs with the bucket."
  }
}

run "only_this_trail_can_write_to_the_bucket" {
  command = plan

  assert {
    condition     = strcontains(aws_s3_bucket_policy.audit.policy, "arn:aws:cloudtrail:us-east-1:123456789012:trail/portfolio-live-audit")
    error_message = "The bucket must accept logs only from this trail."
  }

  assert {
    condition     = strcontains(aws_s3_bucket_policy.audit.policy, "AWSLogs/123456789012/*")
    error_message = "The trail may write only under this account's log folder."
  }

  assert {
    condition     = strcontains(aws_s3_bucket_policy.audit.policy, "aws:SecureTransport")
    error_message = "The bucket must refuse requests that are not encrypted in transit."
  }
}

run "the_size_alarm_notifies_the_given_targets" {
  command = plan

  variables {
    alarm_actions = ["arn:aws:sns:us-east-1:123456789012:portfolio-live-run-alerts"]
  }

  assert {
    condition     = aws_cloudwatch_metric_alarm.bucket_size.alarm_actions == toset(["arn:aws:sns:us-east-1:123456789012:portfolio-live-run-alerts"])
    error_message = "The size alarm must notify the targets it is given."
  }

  assert {
    condition     = aws_cloudwatch_metric_alarm.bucket_size.dimensions["BucketName"] == "portfolio-live-audit-123456789012"
    error_message = "The size alarm must watch the log bucket."
  }
}

run "the_account_is_checked_for_anything_shared_outside_it" {
  command = plan

  assert {
    condition     = aws_accessanalyzer_analyzer.external_access.type == "ACCOUNT"
    error_message = "The analyzer must look at this account, the free external access kind."
  }
}
