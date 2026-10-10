# Plan-only tests with a mock AWS provider. No AWS calls are made.
# Run from the module folder: terraform init -backend=false, then terraform test.

mock_provider "aws" {}

run "table_is_inside_the_free_tier" {
  command = plan

  variables {
    env = "dev"
  }

  assert {
    condition     = aws_dynamodb_table.visitor.billing_mode == "PROVISIONED"
    error_message = "The visitor table must use provisioned billing."
  }

  assert {
    condition     = aws_dynamodb_table.visitor.read_capacity == 5 && aws_dynamodb_table.visitor.write_capacity == 5
    error_message = "The visitor table must use 5 read and 5 write units."
  }
}

run "point_in_time_recovery_is_on" {
  command = plan

  variables {
    env = "dev"
  }

  assert {
    condition     = aws_dynamodb_table.visitor.point_in_time_recovery[0].enabled == true
    error_message = "Point-in-time recovery must be on."
  }
}

run "live_table_has_deletion_protection" {
  command = plan

  variables {
    env = "live"
  }

  assert {
    condition     = aws_dynamodb_table.visitor.deletion_protection_enabled == true
    error_message = "The live visitor table must be protected from deletion."
  }
}

run "dev_table_can_be_deleted" {
  command = plan

  variables {
    env = "dev"
  }

  assert {
    condition     = aws_dynamodb_table.visitor.deletion_protection_enabled == false
    error_message = "The dev visitor table must not be protected from deletion."
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
