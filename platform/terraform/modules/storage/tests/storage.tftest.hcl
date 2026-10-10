# Plan-only tests with a mock AWS provider. No AWS calls are made.
# Run from the module folder: terraform init -backend=false, then terraform test.

mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
    }
  }
}

run "dev_buckets_are_not_object_locked" {
  command = plan

  variables {
    env = "dev"
  }

  assert {
    condition     = aws_s3_bucket.this["raw"].object_lock_enabled == false
    error_message = "Dev raw bucket must not use Object Lock."
  }

  assert {
    condition     = length(aws_s3_bucket_object_lock_configuration.raw_live) == 0
    error_message = "Dev must have no Object Lock configuration."
  }
}

run "live_raw_bucket_is_locked_for_30_days_in_governance_mode" {
  command = plan

  variables {
    env = "live"
  }

  assert {
    condition     = aws_s3_bucket.this["raw"].object_lock_enabled == true
    error_message = "Live raw bucket must enable Object Lock at creation."
  }

  assert {
    condition     = aws_s3_bucket_object_lock_configuration.raw_live["raw"].rule[0].default_retention[0].mode == "GOVERNANCE"
    error_message = "Live raw Object Lock must use GOVERNANCE mode."
  }

  assert {
    condition     = aws_s3_bucket_object_lock_configuration.raw_live["raw"].rule[0].default_retention[0].days == 30
    error_message = "Live raw Object Lock must last 30 days."
  }
}

run "live_lake_and_site_are_not_locked" {
  command = plan

  variables {
    env = "live"
  }

  assert {
    condition     = aws_s3_bucket.this["lake"].object_lock_enabled == false
    error_message = "Live lake bucket must not use Object Lock."
  }

  assert {
    condition     = aws_s3_bucket.this["site"].object_lock_enabled == false
    error_message = "Live site bucket must not use Object Lock."
  }
}

run "dev_data_expires_after_14_days" {
  command = plan

  variables {
    env = "dev"
  }

  assert {
    condition     = length([for r in aws_s3_bucket_lifecycle_configuration.this["lake"].rule : r if r.id == "dev-data-14-days"]) == 1
    error_message = "Dev lake bucket must expire data after 14 days."
  }

  assert {
    condition     = [for r in aws_s3_bucket_lifecycle_configuration.this["lake"].rule : r if r.id == "dev-data-14-days"][0].expiration[0].days == 14
    error_message = "The dev expiry must be 14 days."
  }
}

run "live_data_has_no_dev_expiry" {
  command = plan

  variables {
    env = "live"
  }

  assert {
    condition     = length([for r in aws_s3_bucket_lifecycle_configuration.this["lake"].rule : r if r.id == "dev-data-14-days"]) == 0
    error_message = "Live data must never expire under the dev rule."
  }
}

run "temporary_files_expire_after_7_days" {
  command = plan

  variables {
    env = "live"
  }

  assert {
    condition     = [for r in aws_s3_bucket_lifecycle_configuration.this["lake"].rule : r if r.id == "temporary-files"][0].expiration[0].days == 7
    error_message = "Files under tmp/ must expire after 7 days."
  }

  assert {
    condition     = [for r in aws_s3_bucket_lifecycle_configuration.this["lake"].rule : r if r.id == "temporary-files"][0].filter[0].prefix == "tmp/"
    error_message = "The temporary-file rule must match the tmp/ prefix."
  }
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
