output "api_url" {
  description = "Base URL of the HTTP API. The site reads it as VITE_API_BASE_URL."
  value       = aws_apigatewayv2_api.http.api_endpoint
}

output "function_name" {
  description = "Name of the API function."
  value       = aws_lambda_function.api.function_name
}
