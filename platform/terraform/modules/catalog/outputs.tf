output "database_name" {
  description = "Name of the Glue database, portfolio_dev or portfolio_live."
  value       = aws_glue_catalog_database.this.name
}

output "database_arn" {
  description = "ARN of the Glue database."
  value       = aws_glue_catalog_database.this.arn
}
