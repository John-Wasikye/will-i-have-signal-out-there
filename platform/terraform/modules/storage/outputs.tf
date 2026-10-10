output "bucket_names" {
  description = "Map of bucket role (raw, lake, site) to bucket name."
  value       = { for key, bucket in aws_s3_bucket.this : key => bucket.id }
}

output "bucket_arns" {
  description = "Map of bucket role (raw, lake, site) to bucket ARN."
  value       = { for key, bucket in aws_s3_bucket.this : key => bucket.arn }
}

output "bucket_regional_domain_names" {
  description = "Map of bucket role (raw, lake, site) to regional domain name. CloudFront uses the site one as its origin."
  value       = { for key, bucket in aws_s3_bucket.this : key => bucket.bucket_regional_domain_name }
}
