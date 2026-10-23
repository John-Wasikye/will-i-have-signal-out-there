variable "limit_usd" {
  description = "Monthly cost limit in US dollars for the whole AWS account."
  type        = number
  default     = 40
}

variable "alert_emails" {
  description = "Email addresses that receive budget alerts at 80 percent actual and 100 percent forecast. Empty means the budget exists but sends no alerts. Sensitive, so plans in public Actions logs hide them."
  type        = list(string)
  default     = []
  sensitive   = true
}
