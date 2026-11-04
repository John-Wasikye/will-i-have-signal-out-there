# Plan-only tests for the custom domain, with a mock AWS provider. No AWS calls are made.
# The domain is added in two phases: first the certificate is requested, then the domain is attached.

mock_provider "aws" {}

variables {
  env                         = "dev"
  bucket_regional_domain_name = "portfolio-dev-site-123456789012.s3.us-east-1.amazonaws.com"
}

run "without_a_domain_the_default_certificate_is_kept" {
  command = plan

  assert {
    condition     = length(aws_acm_certificate.site) == 0
    error_message = "No certificate may be requested when no site domain is set."
  }

  assert {
    condition     = length(aws_cloudfront_distribution.site.aliases) == 0
    error_message = "The distribution must not claim any alias when no site domain is set."
  }

  assert {
    condition     = aws_cloudfront_distribution.site.viewer_certificate[0].cloudfront_default_certificate == true
    error_message = "Without a site domain, CloudFront must keep its default certificate."
  }
}

run "without_a_domain_no_cloudflare_records_are_printed" {
  command = plan

  assert {
    condition     = length(output.dns_record_1_certificate_validation) == 0
    error_message = "With no site domain there is no validation record to print."
  }

  assert {
    condition     = output.dns_record_2_site == null
    error_message = "With no site domain there is no site record to print."
  }
}

# Phase 1: the certificate is requested, but the site is not yet served under the domain.
run "a_domain_gets_a_certificate_before_it_is_attached" {
  command = plan

  variables {
    site_domain = "signal.johnwasikye.com"
  }

  assert {
    condition     = length(aws_acm_certificate.site) == 1 && aws_acm_certificate.site[0].domain_name == "signal.johnwasikye.com"
    error_message = "A site domain must get one certificate for that exact name."
  }

  assert {
    condition     = aws_acm_certificate.site[0].validation_method == "DNS"
    error_message = "The certificate must be validated by a DNS record, since Cloudflare holds the zone."
  }

  assert {
    condition     = length(aws_acm_certificate_validation.site) == 0
    error_message = "The certificate must not be waited on before the validation record is in DNS."
  }

  assert {
    condition     = length(aws_cloudfront_distribution.site.aliases) == 0
    error_message = "The distribution must not use the domain before attach_domain is true."
  }

  assert {
    condition     = aws_cloudfront_distribution.site.viewer_certificate[0].cloudfront_default_certificate == true
    error_message = "Until the domain is attached, CloudFront must keep its default certificate."
  }
}

run "attaching_a_domain_without_a_site_domain_is_refused" {
  command = plan

  variables {
    attach_domain = true
  }

  expect_failures = [
    var.attach_domain,
  ]
}

# Phase 2: once the certificate is issued, CloudFront serves the domain with it.
run "an_attached_domain_is_served_with_the_validated_certificate" {
  command = apply

  variables {
    site_domain   = "signal.johnwasikye.com"
    attach_domain = true
  }

  # The mock makes up a function ARN that CloudFront refuses, so it is fixed here, as in site.tftest.hcl.
  override_resource {
    target = aws_cloudfront_function.block_published
    values = {
      arn = "arn:aws:cloudfront::123456789012:function/portfolio-dev-block-published"
    }
  }

  override_resource {
    target = aws_acm_certificate.site[0]
    values = {
      arn = "arn:aws:acm:us-east-1:123456789012:certificate/11111111-2222-3333-4444-555555555555"
    }
  }

  assert {
    condition     = contains(aws_cloudfront_distribution.site.aliases, "signal.johnwasikye.com")
    error_message = "The distribution must answer for the site domain once it is attached."
  }

  assert {
    condition     = aws_cloudfront_distribution.site.viewer_certificate[0].acm_certificate_arn == aws_acm_certificate_validation.site[0].certificate_arn
    error_message = "The distribution must use the validated certificate."
  }

  assert {
    condition     = aws_cloudfront_distribution.site.viewer_certificate[0].ssl_support_method == "sni-only"
    error_message = "The certificate must be served with SNI, which needs no dedicated IP address."
  }

  assert {
    condition     = aws_cloudfront_distribution.site.viewer_certificate[0].minimum_protocol_version == "TLSv1.2_2021"
    error_message = "Browsers must negotiate at least TLS 1.2."
  }

  assert {
    condition     = aws_cloudfront_distribution.site.viewer_certificate[0].cloudfront_default_certificate != true
    error_message = "The default certificate must be dropped once the domain is attached."
  }
}

# The site record to add at Cloudflare, as the output prints it. The validation record's output
# is not checked here: the mock provider leaves domain_validation_options empty.
run "the_site_record_for_cloudflare_is_output" {
  command = apply

  variables {
    site_domain   = "signal.johnwasikye.com"
    attach_domain = true
  }

  override_resource {
    target = aws_cloudfront_function.block_published
    values = {
      arn = "arn:aws:cloudfront::123456789012:function/portfolio-dev-block-published"
    }
  }

  override_resource {
    target = aws_acm_certificate.site[0]
    values = {
      arn = "arn:aws:acm:us-east-1:123456789012:certificate/11111111-2222-3333-4444-555555555555"
    }
  }

  assert {
    condition     = output.dns_record_2_site.name == "signal.johnwasikye.com" && output.dns_record_2_site.target == aws_cloudfront_distribution.site.domain_name && output.dns_record_2_site.type == "CNAME"
    error_message = "The site record must be a CNAME from the site domain to the distribution."
  }
}
