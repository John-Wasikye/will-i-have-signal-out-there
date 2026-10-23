variable "env" {
  description = "Environment name. Must be dev or live."
  type        = string

  validation {
    condition     = contains(["dev", "live"], var.env)
    error_message = "The env variable must be either \"dev\" or \"live\"."
  }
}

variable "github_repo" {
  description = "GitHub repository whose workflows may use these roles, in owner/name form."
  type        = string
  default     = "John-Wasikye/will-i-have-signal-out-there"

  validation {
    condition     = can(regex("^[^/]+/[^/]+$", var.github_repo))
    error_message = "The github_repo variable must look like owner/name."
  }
}

variable "site_bucket_arn" {
  description = "ARN of this environment's site bucket. The deploy role uploads the site build here."
  type        = string
}

variable "distribution_arn" {
  description = "ARN of this environment's CloudFront distribution. The deploy role clears its cache after an upload."
  type        = string
}

variable "registry_arn" {
  description = "ARN of this environment's image repository. The deploy role pushes the Airflow image here."
  type        = string
}

variable "protected_arns" {
  description = "ARN patterns of other projects in the same AWS account. Both apply roles are refused every action on them, because their broad rights would otherwise reach those projects."
  type        = list(string)
  default     = []
}