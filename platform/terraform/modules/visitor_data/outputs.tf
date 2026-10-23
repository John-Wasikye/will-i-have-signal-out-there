output "table_name" {
  description = "Name of the visitor DynamoDB table."
  value       = aws_dynamodb_table.visitor.name
}

output "table_arn" {
  description = "ARN of the visitor DynamoDB table."
  value       = aws_dynamodb_table.visitor.arn
}
