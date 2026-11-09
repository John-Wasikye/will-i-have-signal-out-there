# Report API (C22): POST /reports runs its own small function, apart from the read-only API.
# It is the first public write route, so it gets its own role, which can only add reports and
# count limits, and its own tighter throttle. The code is reports.py in the same package.

data "aws_region" "current" {}

data "aws_caller_identity" "current" {}

locals {
  reports_name          = "portfolio-${var.env}-reports"
  reports_table         = "portfolio-${var.env}-signal-reports"
  report_limits_table   = "portfolio-${var.env}-signal-report-limits"
  visitor_key_parameter = "/portfolio/${var.env}/signal/report-visitor-key"
  dynamodb_arn_prefix   = "arn:${local.partition}:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table"
}

# --- Tables --------------------------------------------------------------------------------

# One item per accepted report, with no visitor ID (contract hiker_signal_reports).
# Provisioned capacity inside the free tier: a flood is throttled instead of billed.
# Point-in-time recovery is off so a report is really gone 30 days after the nightly copy
# sets expires_at_epoch (ADR 0012, ADR 0022).
resource "aws_dynamodb_table" "signal_reports" {
  name           = local.reports_table
  billing_mode   = "PROVISIONED"
  read_capacity  = 1
  write_capacity = 2
  hash_key       = "report_id"

  attribute {
    name = "report_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at_epoch"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = false
  }

  server_side_encryption {
    enabled = true
  }

  deletion_protection_enabled = var.env == "live"
}

# Limit counters, kept apart from the reports. Keys hold only keyed hashes of the visitor ID,
# and counters expire 72 hours after their UTC day (ADR 0025, ADR 0026). Recovery is off so
# a hash does not outlive its expiry (OQ-41). A report's transaction writes three items here,
# each at twice the normal cost, so this table gets more write capacity than the reports.
resource "aws_dynamodb_table" "report_limits" {
  name           = local.report_limits_table
  billing_mode   = "PROVISIONED"
  read_capacity  = 1
  write_capacity = 5
  hash_key       = "counter_key"

  attribute {
    name = "counter_key"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at_epoch"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = false
  }

  server_side_encryption {
    enabled = true
  }

  deletion_protection_enabled = var.env == "live"
}

# --- The function's role -------------------------------------------------------------------

resource "aws_iam_role" "reports" {
  name               = local.reports_name
  description        = "Role for the ${var.env} report function."
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

# A transaction checks each item's own action: Put on the reports table, Update and Put on
# the counters. GetItem reads the hours a visitor already reported at one place. No delete,
# scan or query, so the function cannot read reports back or list counters.
data "aws_iam_policy_document" "reports_store" {
  statement {
    sid       = "AddReports"
    effect    = "Allow"
    actions   = ["dynamodb:PutItem"]
    resources = ["${local.dynamodb_arn_prefix}/${local.reports_table}"]
  }

  statement {
    sid       = "CountLimits"
    effect    = "Allow"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
    resources = ["${local.dynamodb_arn_prefix}/${local.report_limits_table}"]
  }

  statement {
    sid       = "ReadVisitorKey"
    effect    = "Allow"
    actions   = ["ssm:GetParameter"]
    resources = ["arn:${local.partition}:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${local.visitor_key_parameter}"]
  }

  statement {
    sid       = "WriteOwnLogs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:${local.partition}:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${local.reports_name}:*"]
  }
}

resource "aws_iam_role_policy" "reports_store" {
  name   = "reports-store"
  role   = aws_iam_role.reports.id
  policy = data.aws_iam_policy_document.reports_store.json
}

# --- The function --------------------------------------------------------------------------

# Kept 7 days (ADR 0029). The code logs only the kind of a failure, never the request.
resource "aws_cloudwatch_log_group" "reports" {
  name              = "/aws/lambda/${local.reports_name}"
  retention_in_days = 7
}

# Same package as the read-only API; only the handler differs. No reserved concurrency: the
# account's whole Lambda limit is 10 and AWS keeps 10 unreserved, so the route's throttle and
# the 50-a-day limit are the caps (ADR 0029 asks for 10 once the account limit allows it).
resource "aws_lambda_function" "reports" {
  function_name = local.reports_name
  role          = aws_iam_role.reports.arn
  runtime       = "python3.12"
  architectures = ["arm64"]
  handler       = "reports.handler"

  filename         = var.lambda_zip_path
  source_code_hash = var.lambda_zip_sha256

  memory_size = 256
  timeout     = 5

  environment {
    variables = {
      REPORTS_TABLE         = aws_dynamodb_table.signal_reports.name
      COUNTERS_TABLE        = aws_dynamodb_table.report_limits.name
      VISITOR_KEY_PARAMETER = local.visitor_key_parameter
    }
  }

  depends_on = [aws_cloudwatch_log_group.reports]
}

# --- The route -----------------------------------------------------------------------------

resource "aws_apigatewayv2_integration" "reports" {
  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.reports.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "reports" {
  api_id    = aws_apigatewayv2_api.http.id
  route_key = "POST /reports"
  target    = "integrations/${aws_apigatewayv2_integration.reports.id}"
}

resource "aws_lambda_permission" "reports_from_api_gateway" {
  statement_id  = "AllowInvokeFromApiGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.reports.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/POST/reports"
}
