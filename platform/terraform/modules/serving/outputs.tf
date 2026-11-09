output "api_url" {
  description = "Base URL of the HTTP API. The site reads it as VITE_API_BASE_URL."
  value       = aws_apigatewayv2_api.http.api_endpoint
}

output "function_name" {
  description = "Name of the API function."
  value       = aws_lambda_function.api.function_name
}

output "reports_function_name" {
  description = "Name of the report function (POST /reports)."
  value       = aws_lambda_function.reports.function_name
}

output "report_table_names" {
  description = "The reports table and the limit counters table."
  value = {
    reports  = aws_dynamodb_table.signal_reports.name
    counters = aws_dynamodb_table.report_limits.name
  }
}

output "visitor_key_parameter" {
  description = "Parameter Store name of the report function's HMAC key. Written by hand, never by Terraform."
  value       = local.visitor_key_parameter
}
