terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

locals {
  # Budget notifications need at least one subscriber, and a notification block cannot use count.
  # The dynamic block below therefore creates no notifications when alert_emails is empty.
  notifications = {
    actual_80 = {
      threshold = 80
      type      = "ACTUAL"
    }
    forecast_100 = {
      threshold = 100
      type      = "FORECASTED"
    }
  }
}

# The budget name is account-wide, so envs/live is the only caller.
#
# Budget actions (automatic launch denial and stopping the session box) are a backup only.
# Budget alerts lag by hours, so they are not configured here. The 4-hour session limit and
# the idle alarm on the session box are the real cost guards (ADR-0013).
resource "aws_budgets_budget" "monthly" {
  name         = "portfolio-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = length(var.alert_emails) > 0 ? local.notifications : {}

    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value.threshold
      threshold_type             = "PERCENTAGE"
      notification_type          = notification.value.type
      subscriber_email_addresses = var.alert_emails
    }
  }
}
