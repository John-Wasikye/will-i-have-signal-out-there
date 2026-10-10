variable "env" {
  description = "Environment name. Must be dev or live. Used in every bucket name."
  type        = string

  validation {
    condition     = contains(["dev", "live"], var.env)
    error_message = "The env variable must be either \"dev\" or \"live\"."
  }
}

variable "size_alarm_bytes" {
  description = "Bucket size in bytes that raises the size alarm. The default is 100 GB."
  type        = number
  default     = 107374182400
}

variable "alarm_actions" {
  description = "ARNs of SNS topics or other targets notified when a size alarm fires. Empty means the alarm only changes state."
  type        = list(string)
  default     = []
}

variable "site_distribution_arn" {
  description = "ARN of the CloudFront distribution that serves the site. When set, only this distribution may read the site bucket. Leave it null before the distribution exists."
  type        = string
  default     = null
}
