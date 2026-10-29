# Plan-only tests with a mock AWS provider. No AWS calls are made.
# Run from the module folder: terraform init -backend=false, then terraform test.

mock_provider "aws" {}

variables {
  env                         = "dev"
  bucket_regional_domain_name = "portfolio-dev-site-123456789012.s3.us-east-1.amazonaws.com"
}

run "the_bucket_is_reached_through_private_access_control" {
  command = plan

  assert {
    condition     = aws_cloudfront_origin_access_control.site.signing_behavior == "always"
    error_message = "CloudFront must always sign its requests to the bucket."
  }

  assert {
    condition     = aws_cloudfront_origin_access_control.site.origin_access_control_origin_type == "s3"
    error_message = "The access control must be for an S3 origin."
  }
}

run "every_request_is_sent_to_https" {
  command = plan

  assert {
    condition     = aws_cloudfront_distribution.site.default_cache_behavior[0].viewer_protocol_policy == "redirect-to-https"
    error_message = "Readers on http must be redirected to https."
  }
}

run "the_status_file_is_never_cached" {
  command = plan

  assert {
    condition     = length([for b in aws_cloudfront_distribution.site.ordered_cache_behavior : b if b.path_pattern == "status.json" && b.cache_policy_id == "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"]) == 1
    error_message = "status.json must use the managed policy that disables caching, so the status page is never stale."
  }
}

run "published_data_files_are_not_served_to_the_public" {
  command = plan

  assert {
    condition     = length([for b in aws_cloudfront_distribution.site.ordered_cache_behavior : b if b.path_pattern == "published/*" && length(b.function_association) == 1]) == 1
    error_message = "Requests for published/* must run through a function that blocks them."
  }

  assert {
    condition     = strcontains(aws_cloudfront_function.block_published.code, "statusCode: 403")
    error_message = "The blocking function must answer 403."
  }
}

run "unknown_paths_return_the_app_so_page_links_work" {
  command = plan

  assert {
    condition     = length([for e in aws_cloudfront_distribution.site.custom_error_response : e if e.response_page_path == "/index.html" && e.response_code == 200 && contains([403, 404], e.error_code)]) == 2
    error_message = "A missing path must return index.html with a 200, for both the 403 and 404 that S3 sends."
  }
}

run "the_cheapest_price_class_is_used" {
  command = plan

  assert {
    condition     = aws_cloudfront_distribution.site.price_class == "PriceClass_100"
    error_message = "The distribution must use PriceClass_100, to stay inside the free allowance."
  }
}

run "rejects_an_unknown_environment" {
  command = plan

  variables {
    env = "staging"
  }

  expect_failures = [
    var.env,
  ]
}

# The mock provider fills in IDs only on apply, so this run applies against the mock.
run "the_deploy_can_find_the_distribution_to_clear_its_cache" {
  command = apply

  # The mock makes up an ARN for the function that the distribution refuses, so it is fixed here.
  override_resource {
    target = aws_cloudfront_function.block_published
    values = {
      arn = "arn:aws:cloudfront::123456789012:function/portfolio-dev-block-published"
    }
  }
  assert {
    condition     = output.distribution_id == aws_cloudfront_distribution.site.id
    error_message = "The module must output the distribution ID, which the deploy workflow needs."
  }
}
run "every_response_carries_the_security_headers" {
  # Apply against the mock provider, so the policy gets an ID the behaviors can be compared to.
  command = apply

  assert {
    condition = alltrue([
      for id in concat(
        [aws_cloudfront_distribution.site.default_cache_behavior[0].response_headers_policy_id],
        [for b in aws_cloudfront_distribution.site.ordered_cache_behavior : b.response_headers_policy_id],
      ) : id == aws_cloudfront_response_headers_policy.security.id
    ])
    error_message = "Every cache behavior must send the security headers policy."
  }

  assert {
    condition     = aws_cloudfront_response_headers_policy.security.security_headers_config[0].strict_transport_security[0].access_control_max_age_sec >= 31536000
    error_message = "Browsers must be told to use https for at least a year."
  }

  assert {
    condition     = aws_cloudfront_response_headers_policy.security.security_headers_config[0].frame_options[0].frame_option == "DENY"
    error_message = "No other site may show this site in a frame."
  }

  assert {
    condition     = aws_cloudfront_response_headers_policy.security.security_headers_config[0].content_type_options[0].override
    error_message = "Browsers must not guess file types."
  }

  assert {
    condition = alltrue([
      for rule in ["default-src 'self'", "object-src 'none'", "frame-ancestors 'none'", "base-uri 'self'"] :
      strcontains(aws_cloudfront_response_headers_policy.security.security_headers_config[0].content_security_policy[0].content_security_policy, rule)
    ])
    error_message = "The content security policy must allow only this site's own files."
  }
}
