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
    condition     = aws_apigatewayv2_api.http.cors_configuration[0].allow_methods == toset(["GET", "OPTIONS"])
    error_message = "The public API is read-only, so it allows only GET and OPTIONS."
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
