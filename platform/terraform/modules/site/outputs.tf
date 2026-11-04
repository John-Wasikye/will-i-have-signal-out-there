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

output "dns_record_1_certificate_validation" {
  description = "Add this CNAME at Cloudflare as DNS only (grey cloud), so AWS can issue the certificate. Keyed by domain name."
  value = var.site_domain == null ? {} : {
    for option in aws_acm_certificate.site[0].domain_validation_options : option.domain_name => {
      type   = option.resource_record_type
      name   = option.resource_record_name
      target = option.resource_record_value
    }
  }
}

output "dns_record_2_site" {
  description = "Add this CNAME at Cloudflare as DNS only (grey cloud) once attach_domain is true. Points the site domain at the distribution."
  value = var.site_domain == null ? null : {
    type   = "CNAME"
    name   = var.site_domain
    target = aws_cloudfront_distribution.site.domain_name
  }
}

output "origins" {
  description = "Addresses the site is served from, for the serving API's allowed_origins. The cloudfront.net address always, and https://<site_domain> once attach_domain is true."
  value = concat(
    ["https://${aws_cloudfront_distribution.site.domain_name}"],
    var.attach_domain ? ["https://${var.site_domain}"] : [],
  )
}
