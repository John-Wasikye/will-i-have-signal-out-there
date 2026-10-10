locals {
  name      = "portfolio-${var.env}-site"
  origin_id = "site-bucket"

  # AWS managed cache policies. Their IDs are fixed and the same in every account.
  caching_optimized_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  caching_disabled_policy_id  = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
}

# CloudFront signs its requests to the bucket, so the bucket can stay fully private.
resource "aws_cloudfront_origin_access_control" "site" {
  name                              = local.name
  description                       = "Lets the ${var.env} site distribution read the private site bucket."
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# The Lambda function reads the Parquet files in published/ straight from the bucket.
# Readers have no use for them, so CloudFront refuses any request for that folder.
resource "aws_cloudfront_function" "block_published" {
  name    = "${local.name}-block-published"
  runtime = "cloudfront-js-2.0"
  comment = "Answers 403 for any request under published/."
  publish = true
  code    = <<-JS
    function handler(event) {
      return { statusCode: 403, statusDescription: 'Forbidden' };
    }
  JS
}

resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  comment             = "${var.env} site"
  default_root_object = "index.html"
  price_class         = "PriceClass_100"
  http_version        = "http2and3"
  is_ipv6_enabled     = true

  origin {
    domain_name              = var.bucket_regional_domain_name
    origin_id                = local.origin_id
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  default_cache_behavior {
    target_origin_id       = local.origin_id
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = local.caching_optimized_policy_id
  }

  # The status page must show the latest run, so status.json is never cached.
  ordered_cache_behavior {
    path_pattern           = "status.json"
    target_origin_id       = local.origin_id
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = local.caching_disabled_policy_id
  }

  ordered_cache_behavior {
    path_pattern           = "published/*"
    target_origin_id       = local.origin_id
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = local.caching_disabled_policy_id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.block_published.arn
    }
  }

  # With private access, S3 answers 403 for a missing file. The app handles its own page
  # links in the browser, so a missing path returns the app, not an error.
  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}
