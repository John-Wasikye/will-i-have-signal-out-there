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

output "session_box_instance_id" {
  description = "ID of the session box."
  value       = module.session_box.instance_id
}

output "site_url" {
  description = "Address of the site."
  value       = "https://${module.site.domain_name}"
}

output "api_url" {
  description = "Base URL of the API."
  value       = module.serving.api_url
}

output "airflow_image_repository" {
  description = "Address of the Airflow image repository. The install script takes it as IMAGE_REPOSITORY."
  value       = module.registry.repository_url
}

output "alert_topic_arn" {
  description = "Run alerts topic. The install script takes it as ALERT_TOPIC_ARN."
  value       = module.alerts.topic_arn
}
