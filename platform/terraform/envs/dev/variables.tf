variable "region" {
  description = "AWS region for the dev environment."
  type        = string
  default     = "us-east-1"
}

variable "github_repo" {
  description = "GitHub repository allowed to assume the dev pipeline roles, in owner/name form."
  type        = string
  default     = "John-Wasikye/will-i-have-signal-out-there"
}

variable "pipeline_names" {
  description = "Pipelines that each get a dev role, for example platform_skeleton."
  type        = list(string)
  default     = ["platform_skeleton"]
}

variable "size_alarm_bytes" {
  description = "Bucket size in bytes that raises the size alarm on each dev bucket. The default is 100 GB."
  type        = number
  default     = 107374182400
}
