variable "region" {
  description = "AWS region for the live environment."
  type        = string
  default     = "us-east-1"
}

variable "github_repo" {
  description = "GitHub repository allowed to assume the live pipeline roles, in owner/name form. Live roles accept only the main branch."
  type        = string
  default     = "jwasikye/will-i-have-signal-out-there"
}

variable "pipeline_names" {
  description = "Pipelines that each get a live role, for example platform_skeleton."
  type        = list(string)
  default     = ["platform_skeleton"]
}

variable "size_alarm_bytes" {
  description = "Bucket size in bytes that raises the size alarm on each live bucket. The default is 100 GB."
  type        = number
  default     = 107374182400
}

variable "alarm_actions" {
  description = "ARNs of SNS topics notified when a live bucket size alarm fires. Empty means the alarm only changes state."
  type        = list(string)
  default     = []
}

variable "budget_limit_usd" {
  description = "Monthly cost limit in US dollars for the whole AWS account."
  type        = number
  default     = 40
}

variable "alert_emails" {
  description = "Email addresses that receive budget alerts. Empty means the budget exists but sends no alerts."
  type        = list(string)
  default     = []
}
