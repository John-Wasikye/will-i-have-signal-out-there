# Plan-only tests. No AWS calls are made.
# The real provider runs so the policy documents build real JSON. Only the partition lookup,
# which needs an AWS account, is overridden with a fixed value.
# Run from the module folder: terraform init -backend=false, then terraform test.

provider "aws" {
  region                      = "us-east-1"
  access_key                  = "not-a-real-key"
  secret_key                  = "not-a-real-secret"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
}

# The report function's policy names its tables and parameter by full ARN, which needs the
# region and account. Both lookups are fixed here for every run.
override_data {
  target = data.aws_region.current
  values = {
    name = "us-east-1"
  }
}

override_data {
  target = data.aws_caller_identity.current
  values = {
    account_id = "123456789012"
  }
}

variables {
  env               = "dev"
  published_bucket  = "portfolio-dev-site-123456789012"
  lambda_zip_path   = "tests/fixtures/function.zip"
  lambda_zip_sha256 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
  allowed_origins   = ["https://example.com"]
}

run "function_runs_on_arm_with_the_fastapi_handler" {
  command = plan


  override_data {
    target = data.aws_partition.current
    values = {
      partition = "aws"
    }
  }


  assert {
    condition     = aws_lambda_function.api.architectures[0] == "arm64"
    error_message = "The function must run on arm64, like every other image in the platform."
  }

  assert {
    condition     = aws_lambda_function.api.handler == "handler.handler"
    error_message = "The function must use the Mangum handler in handler.py."
  }
}

run "concurrency_is_capped_so_traffic_cannot_run_up_a_bill" {
  command = plan


  override_data {
    target = data.aws_partition.current
    values = {
      partition = "aws"
    }
  }


  assert {
    condition     = aws_lambda_function.api.reserved_concurrent_executions == 10
    error_message = "The default cap must be 10 copies of the function at once."
  }
}

# An account whose whole Lambda limit is 10 cannot reserve 10 for one function: AWS keeps at
# least 10 unreserved. There the account limit is already the cap, so no reservation is set.
run "no_reservation_where_the_account_limit_is_already_the_cap" {
  command = plan

  override_data {
    target = data.aws_partition.current
    values = {
      partition = "aws"
    }
  }

  variables {
    reserved_concurrency = null
  }

  assert {
    condition     = aws_lambda_function.api.reserved_concurrent_executions == -1
    error_message = "With no reservation the function must use the account's unreserved pool (-1)."
  }
}

run "api_throttles_requests" {
  command = plan


  override_data {
    target = data.aws_partition.current
    values = {
      partition = "aws"
    }
  }


  assert {
    condition     = aws_apigatewayv2_stage.default.default_route_settings[0].throttling_rate_limit == 20
    error_message = "The API must limit the steady request rate."
  }

  assert {
    condition     = aws_apigatewayv2_stage.default.default_route_settings[0].throttling_burst_limit == 40
    error_message = "The API must limit bursts."
  }
}

run "function_can_only_read_published_files" {
  command = plan


  override_data {
    target = data.aws_partition.current
    values = {
      partition = "aws"
    }
  }


  assert {
    condition     = strcontains(aws_iam_role_policy.published_read.policy, "s3:GetObject")
    error_message = "The function must be able to read published files."
  }

  assert {
    condition     = !strcontains(aws_iam_role_policy.published_read.policy, "s3:PutObject") && !strcontains(aws_iam_role_policy.published_read.policy, "s3:DeleteObject")
    error_message = "The function must not be able to write or delete files."
  }

  assert {
    condition     = strcontains(aws_iam_role_policy.published_read.policy, "portfolio-dev-site-123456789012/published/*")
    error_message = "The function must be limited to the published folder."
  }
}

run "logs_are_kept_for_90_days" {
  command = plan


  override_data {
    target = data.aws_partition.current
    values = {
      partition = "aws"
    }
  }


  assert {
    condition     = aws_cloudwatch_log_group.api.retention_in_days == 90
    error_message = "Pipeline and function logs are kept for 90 days."
  }
}

run "only_the_listed_origins_may_call_the_api_from_a_browser" {
  command = plan


  override_data {
    target = data.aws_partition.current
    values = {
      partition = "aws"
    }
  }


  assert {
    condition     = contains(aws_apigatewayv2_api.http.cors_configuration[0].allow_origins, "https://example.com")
    error_message = "The listed origin must be allowed."
  }

  assert {
    condition     = !contains(aws_apigatewayv2_api.http.cors_configuration[0].allow_origins, "*")
    error_message = "The API must not allow every origin."
  }

  assert {
    condition     = aws_apigatewayv2_api.http.cors_configuration[0].allow_methods == toset(["GET", "OPTIONS", "POST"])
    error_message = "Browsers may read with GET and send reports with POST, nothing else."
  }

  assert {
    condition     = aws_apigatewayv2_api.http.cors_configuration[0].allow_headers == toset(["content-type", "x-visitor-id"])
    error_message = "A report sends its visitor ID in the X-Visitor-Id header, so browsers must be allowed to send it."
  }
}

# --- Report API (C22) ------------------------------------------------------------------------

run "reports_go_to_their_own_small_function" {
  command = plan

  override_data {
    target = data.aws_partition.current
    values = {
      partition = "aws"
    }
  }

  assert {
    condition     = aws_apigatewayv2_route.reports.route_key == "POST /reports"
    error_message = "POST /reports must have its own route."
  }

  assert {
    condition     = aws_lambda_function.reports.handler == "reports.handler"
    error_message = "The report route must run reports.handler, not the read-only API."
  }

  assert {
    condition     = aws_lambda_function.reports.memory_size == 256 && aws_lambda_function.reports.timeout == 5
    error_message = "ADR 0029 starts the report function at 256 MB and 5 seconds."
  }

  assert {
    condition     = aws_lambda_function.reports.architectures[0] == "arm64"
    error_message = "The report function must run on arm64."
  }

  assert {
    condition     = aws_lambda_function.reports.environment[0].variables["VISITOR_KEY_PARAMETER"] == "/portfolio/dev/signal/report-visitor-key"
    error_message = "The function must read its HMAC key from this environment's parameter."
  }
}

run "the_report_route_is_throttled_harder_than_reads" {
  command = plan

  override_data {
    target = data.aws_partition.current
    values = {
      partition = "aws"
    }
  }

  assert {
    condition = anytrue([
      for setting in aws_apigatewayv2_stage.default.route_settings :
      setting.route_key == "POST /reports" && setting.throttling_rate_limit == 10 && setting.throttling_burst_limit == 20
    ])
    error_message = "ADR 0029: POST routes take 10 requests a second with bursts of 20."
  }
}

run "report_tables_have_no_point_in_time_recovery_and_expire_rows" {
  command = plan

  override_data {
    target = data.aws_partition.current
    values = {
      partition = "aws"
    }
  }

  assert {
    condition     = aws_dynamodb_table.signal_reports.name == "portfolio-dev-signal-reports" && aws_dynamodb_table.report_limits.name == "portfolio-dev-signal-report-limits"
    error_message = "Table names follow portfolio-<env>-<name>."
  }

  assert {
    condition     = !aws_dynamodb_table.signal_reports.point_in_time_recovery[0].enabled && !aws_dynamodb_table.report_limits.point_in_time_recovery[0].enabled
    error_message = "Point-in-time recovery stays off, so expired reports and visitor hashes are really gone (ADR 0022, 0025)."
  }

  assert {
    condition     = aws_dynamodb_table.signal_reports.ttl[0].attribute_name == "expires_at_epoch" && aws_dynamodb_table.signal_reports.ttl[0].enabled
    error_message = "Reports must expire on expires_at_epoch, which the nightly copy sets (ADR 0012)."
  }

  assert {
    condition     = aws_dynamodb_table.report_limits.ttl[0].attribute_name == "expires_at_epoch" && aws_dynamodb_table.report_limits.ttl[0].enabled
    error_message = "Counters must expire on expires_at_epoch (ADR 0026)."
  }

  assert {
    condition     = aws_dynamodb_table.signal_reports.billing_mode == "PROVISIONED" && aws_dynamodb_table.report_limits.billing_mode == "PROVISIONED"
    error_message = "Provisioned capacity throttles a flood instead of billing for it."
  }

  assert {
    condition     = aws_dynamodb_table.signal_reports.hash_key == "report_id" && aws_dynamodb_table.report_limits.hash_key == "counter_key"
    error_message = "Keys follow the hiker_signal_reports contract."
  }
}

run "the_report_function_can_only_write_reports_and_counters" {
  command = plan

  override_data {
    target = data.aws_partition.current
    values = {
      partition = "aws"
    }
  }

  assert {
    condition     = strcontains(aws_iam_role_policy.reports_store.policy, "arn:aws:dynamodb:us-east-1:123456789012:table/portfolio-dev-signal-reports")
    error_message = "The function must be able to write the reports table."
  }

  assert {
    condition     = !strcontains(aws_iam_role_policy.reports_store.policy, "dynamodb:DeleteItem") && !strcontains(aws_iam_role_policy.reports_store.policy, "dynamodb:Scan") && !strcontains(aws_iam_role_policy.reports_store.policy, "dynamodb:Query")
    error_message = "The function must not delete, scan or query."
  }

  assert {
    condition     = strcontains(aws_iam_role_policy.reports_store.policy, "arn:aws:ssm:us-east-1:123456789012:parameter/portfolio/dev/signal/report-visitor-key")
    error_message = "The function must read only its own key parameter."
  }

  assert {
    condition     = !strcontains(aws_iam_role_policy.reports_store.policy, "s3:")
    error_message = "The report function has no use for S3."
  }
}

run "report_logs_are_kept_for_7_days" {
  command = plan

  override_data {
    target = data.aws_partition.current
    values = {
      partition = "aws"
    }
  }

  assert {
    condition     = aws_cloudwatch_log_group.reports.retention_in_days == 7
    error_message = "ADR 0029 keeps report logs for 7 days."
  }
}

run "refuses_a_wildcard_origin" {
  command = plan


  override_data {
    target = data.aws_partition.current
    values = {
      partition = "aws"
    }
  }


  variables {
    allowed_origins = ["*"]
  }

  expect_failures = [
    var.allowed_origins,
  ]
}

run "rejects_an_unknown_environment" {
  command = plan


  override_data {
    target = data.aws_partition.current
    values = {
      partition = "aws"
    }
  }


  variables {
    env = "staging"
  }

  expect_failures = [
    var.env,
  ]
}
