variable "env" {
  description = "Environment name. Must be dev or live."
  type        = string

  validation {
    condition     = contains(["dev", "live"], var.env)
    error_message = "The env variable must be either \"dev\" or \"live\"."
  }
}

variable "alert_emails" {
  description = "Email addresses that receive run alerts. Each address must confirm the subscription from the email AWS sends. Empty means the topic exists but emails nobody. Sensitive, so plans in public Actions logs hide them."
  type        = list(string)
  default     = []
  sensitive   = true
}

variable "watched_pipelines" {
  description = "Pipelines that get an alarm when no good run arrives within the freshness target. Leave empty where no nightly schedule runs, or the alarm fires every day."
  type        = list(string)
  default     = []
}

variable "freshness_target_hours" {
  description = "Hours without a good run before the missed-run alarm fires. The skeleton uses 26 (OQ-P08). CloudWatch allows at most a week for hourly periods."
  type        = number
  default     = 26

  validation {
    condition     = var.freshness_target_hours >= 1 && var.freshness_target_hours <= 168 && floor(var.freshness_target_hours) == var.freshness_target_hours
    error_message = "The freshness target must be a whole number of hours from 1 to 168."
  }
}
