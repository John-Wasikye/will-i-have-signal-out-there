variable "region" {
  description = "AWS region for the live environment."
  type        = string
  default     = "us-east-1"
}

variable "github_repo" {
  description = "GitHub repository allowed to assume the live pipeline roles, as owner@owner_id/name@repo_id, the form GitHub puts in its tokens. Live roles accept only the main branch."
  type        = string
  default     = "John-Wasikye@171445038/will-i-have-signal-out-there@1412828974"
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

variable "budget_limit_usd" {
  description = "Monthly cost limit in US dollars for the whole AWS account."
  type        = number
  default     = 40
}

variable "alert_emails" {
  description = "Email addresses that receive budget alerts and run alerts. Each must confirm the subscription email from AWS. Empty means nothing is emailed."
  type        = list(string)
  default     = []
  sensitive   = true
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
