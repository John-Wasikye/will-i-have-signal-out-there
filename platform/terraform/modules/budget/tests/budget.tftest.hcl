# Plan-only tests with a mock AWS provider. No AWS calls are made.
# Run from the module folder: terraform init -backend=false, then terraform test.

mock_provider "aws" {}

run "default_limit_is_40_dollars" {
  command = plan

  assert {
    condition     = aws_budgets_budget.monthly.limit_amount == "40"
    error_message = "The default monthly limit must be 40 US dollars."
  }

  assert {
    condition     = aws_budgets_budget.monthly.name == "portfolio-monthly"
    error_message = "The budget must be named portfolio-monthly."
  }
}

run "no_alerts_without_an_email_address" {
  command = plan

  assert {
    condition     = length(aws_budgets_budget.monthly.notification) == 0
    error_message = "With no alert emails, the budget must send no notifications."
  }
}

run "alerts_at_80_percent_actual_and_100_percent_forecast" {
  command = plan

  variables {
    alert_emails = ["alerts@example.com"]
  }

  assert {
    condition     = length(aws_budgets_budget.monthly.notification) == 2
    error_message = "With an alert email, the budget must send two notifications."
  }

  assert {
    condition     = length([for n in aws_budgets_budget.monthly.notification : n if n.threshold == 80 && n.notification_type == "ACTUAL"]) == 1
    error_message = "There must be an alert at 80 percent of actual spend."
  }

  assert {
    condition     = length([for n in aws_budgets_budget.monthly.notification : n if n.threshold == 100 && n.notification_type == "FORECASTED"]) == 1
    error_message = "There must be an alert at 100 percent of forecast spend."
  }
}
