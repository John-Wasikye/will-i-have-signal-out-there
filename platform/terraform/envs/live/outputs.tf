output "bucket_names" {
  description = "Map of bucket role (raw, lake, site) to live bucket name."
  value       = module.storage.bucket_names
}

output "glue_database_name" {
  description = "Name of the live Glue database."
  value       = module.catalog.database_name
}

output "visitor_table_name" {
  description = "Name of the live visitor DynamoDB table."
  value       = module.visitor_data.table_name
}

output "pipeline_role_arns" {
  description = "Map of pipeline name to live pipeline role ARN."
  value       = module.iam.role_arns
}
