variable "region" {
  description = "AWS region for the live environment."
  type        = string
  default     = "us-east-1"
}

variable "github_repo" {
  description = "GitHub repository allowed to assume the live pipeline roles, in owner/name form. Live roles accept only the main branch."
  type        = string
  default     = "John-Wasikye/will-i-have-signal-out-there"
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

variable "box_ami_id" {
  description = "An arm64 image for the session box. I check its manifest before the first use."
  type        = string
}

variable "box_subnet_id" {
  description = "A public subnet for the session box. There is no NAT gateway."
  type        = string
}

variable "box_security_group_ids" {
  description = "Security groups for the session box. They allow no inbound traffic from the internet."
  type        = list(string)
  default     = []
}

variable "lambda_zip_path" {
  description = "Path to the API package built by platform/serving/build_package.py."
  type        = string
  default     = "../../../serving/build/function.zip"
}

variable "lambda_zip_sha256" {
  description = "Base64 SHA-256 of the API package. The build script prints it."
  type        = string
}
