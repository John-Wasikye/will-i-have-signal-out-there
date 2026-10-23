output "trail_arn" {
  description = "ARN of the account's CloudTrail trail."
  value       = aws_cloudtrail.audit.arn
}

output "bucket_name" {
  description = "Bucket that holds the security logs for one year."
  value       = aws_s3_bucket.audit.id
}
