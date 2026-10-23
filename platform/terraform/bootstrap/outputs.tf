output "state_bucket_name" {
  description = "Name of the Terraform state bucket. Put this in each environment's backend.hcl as bucket."
  value       = aws_s3_bucket.state.id
}

output "state_kms_key_arn" {
  description = "ARN of the customer-managed KMS key that encrypts state. Put this in each environment's backend.hcl as kms_key_id."
  value       = aws_kms_key.state.arn
}
