# Plan-only tests with a mock AWS provider. No AWS calls are made.
# Run from the module folder: terraform init -backend=false, then terraform test.

mock_provider "aws" {}

run "dev_database_is_named_for_dev" {
  command = plan

  variables {
    env = "dev"
  }

  assert {
    condition     = aws_glue_catalog_database.this.name == "portfolio_dev"
    error_message = "The dev Glue database must be named portfolio_dev."
  }
}

run "live_database_is_named_for_live" {
  command = plan

  variables {
    env = "live"
  }

  assert {
    condition     = aws_glue_catalog_database.this.name == "portfolio_live"
    error_message = "The live Glue database must be named portfolio_live."
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
