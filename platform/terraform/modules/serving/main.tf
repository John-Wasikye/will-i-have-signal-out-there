data "aws_partition" "current" {}

data "aws_region" "current" {}

data "aws_caller_identity" "current" {}

locals {
  name      = "portfolio-${var.env}-api"
  partition = data.aws_partition.current.partition
}

# --- The function's role -------------------------------------------------------------------

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "api" {
  name               = local.name
  description        = "Role for the ${var.env} API function."
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

# The function reads published files and nothing else. It cannot write or delete them,
# and it cannot read the raw or lake buckets.
data "aws_iam_policy_document" "published_read" {
  statement {
    sid       = "ListPublishedFolder"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = ["arn:${local.partition}:s3:::${var.published_bucket}"]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["published/*"]
    }
  }

  statement {
    sid       = "ReadPublishedFiles"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["arn:${local.partition}:s3:::${var.published_bucket}/published/*"]
  }
}

resource "aws_iam_role_policy" "published_read" {
  name   = "published-read"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.published_read.json
}

data "aws_iam_policy_document" "logs" {
  statement {
    sid       = "WriteOwnLogs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.api.arn}:*"]
  }
}

resource "aws_iam_role_policy" "logs" {
  name   = "write-own-logs"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.logs.json
}

# --- The function --------------------------------------------------------------------------

# Function logs are kept for 90 days, like pipeline logs.
resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.name}"
  retention_in_days = 90
}

resource "aws_lambda_function" "api" {
  function_name = local.name
  role          = aws_iam_role.api.arn
  runtime       = "python3.12"
  architectures = ["arm64"]
  handler       = "handler.handler"

  filename         = var.lambda_zip_path
  source_code_hash = var.lambda_zip_sha256

  memory_size = var.memory_mb
  timeout     = var.timeout_seconds

  # Caps how many copies run at once, so a spike in traffic cannot run up a bill.
  reserved_concurrent_executions = var.reserved_concurrency

  environment {
    variables = {
      PUBLISHED_BUCKET = var.published_bucket
      PUBLISHED_PREFIX = "published/"
      PUBLISHED_DIR    = "/tmp/published"
    }
  }

  depends_on = [aws_cloudwatch_log_group.api]
}

# --- The public API ------------------------------------------------------------------------

resource "aws_apigatewayv2_api" "http" {
  name          = local.name
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = var.allowed_origins
    allow_methods = ["GET", "OPTIONS"]
    allow_headers = ["content-type"]
    max_age       = 3600
  }
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.http.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_rate_limit  = var.throttle_rate
    throttling_burst_limit = var.throttle_burst
  }
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowInvokeFromApiGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/*"
}
