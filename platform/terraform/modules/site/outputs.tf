output "distribution_arn" {
  description = "ARN of the distribution. Pass it to the storage module so only this distribution can read the site bucket."
  value       = aws_cloudfront_distribution.site.arn
}

output "domain_name" {
  description = "Address of the site, for example d1234abcd.cloudfront.net."
  value       = aws_cloudfront_distribution.site.domain_name
}

output "distribution_id" {
  description = "ID of the distribution. The deploy workflow clears its cache after uploading the site."
  value       = aws_cloudfront_distribution.site.id
}