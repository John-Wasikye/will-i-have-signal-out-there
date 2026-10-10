# Plan-only tests. No AWS calls are made.
# The real provider runs so the bucket policies build real JSON. Only the account lookup is
# overridden with a fixed value.
# Run from the module folder: terraform init -backend=false, then terraform test.

provider "aws" {
  region                      = "us-east-1"
  access_key                  = "not-a-real-key"
  secret_key                  = "not-a-real-secret"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
}

run "every_bucket_denies_requests_without_tls" {
  command = plan

  override_data {
    target = data.aws_caller_identity.current
    values = {
      account_id = "123456789012"
    }
  }

  override_data {
    target = data.aws_partition.current
    values = {
      partition = "aws"
    }
  }

  variables {
    env = "dev"
  }

  assert {
    condition     = strcontains(aws_s3_bucket_policy.this["raw"].policy, "aws:SecureTransport")
    error_message = "The raw bucket must deny requests without TLS."
  }

  assert {
    condition     = strcontains(aws_s3_bucket_policy.this["site"].policy, "aws:SecureTransport")
    error_message = "The site bucket must deny requests without TLS."
  }
}

run "no_cloudfront_access_without_a_distribution" {
  command = plan

  override_data {
    target = data.aws_caller_identity.current
    values = {
      account_id = "123456789012"
    }
  }

  override_data {
    target = data.aws_partition.current
    values = {
      partition = "aws"
    }
  }

  variables {
    env = "dev"
  }

  assert {
    condition     = !strcontains(aws_s3_bucket_policy.this["site"].policy, "cloudfront.amazonaws.com")
    error_message = "With no distribution, the site bucket must not allow CloudFront."
  }
}

run "site_bucket_allows_only_the_given_distribution_to_read" {
  command = plan

  override_data {
    target = data.aws_caller_identity.current
    values = {
      account_id = "123456789012"
    }
  }

  override_data {
    target = data.aws_partition.current
    values = {
      partition = "aws"
    }
  }

  variables {
    env                   = "dev"
    site_distribution_arn = "arn:aws:cloudfront::123456789012:distribution/E1ABCDEFGHIJKL"
  }

  assert {
    condition     = strcontains(aws_s3_bucket_policy.this["site"].policy, "cloudfront.amazonaws.com")
    error_message = "The site bucket must allow CloudFront to read."
  }

  assert {
    condition     = strcontains(aws_s3_bucket_policy.this["site"].policy, "arn:aws:cloudfront::123456789012:distribution/E1ABCDEFGHIJKL")
    error_message = "Only the given distribution may read the site bucket."
  }

  assert {
    condition     = strcontains(aws_s3_bucket_policy.this["site"].policy, "aws:SecureTransport")
    error_message = "The TLS rule must stay in the policy next to the CloudFront rule."
  }
}

run "raw_and_lake_buckets_never_allow_cloudfront" {
  command = plan

  override_data {
    target = data.aws_caller_identity.current
    values = {
      account_id = "123456789012"
    }
  }

  override_data {
    target = data.aws_partition.current
    values = {
      partition = "aws"
    }
  }

  variables {
    env                   = "dev"
    site_distribution_arn = "arn:aws:cloudfront::123456789012:distribution/E1ABCDEFGHIJKL"
  }

  assert {
    condition     = !strcontains(aws_s3_bucket_policy.this["raw"].policy, "cloudfront.amazonaws.com") && !strcontains(aws_s3_bucket_policy.this["lake"].policy, "cloudfront.amazonaws.com")
    error_message = "Only the site bucket may be readable through CloudFront."
  }
}
