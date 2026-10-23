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

variable "protected_names" {
  description = "Name fragments of other projects in the same AWS account, for example nfl-. Both apply roles are refused every resource whose name contains one, in each service the module lists, because their broad rights would otherwise reach those projects."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for name in var.protected_names : can(regex("^[A-Za-z0-9_-]+$", name))])
    error_message = "Each protected name must be letters, digits, '-' or '_', with no wildcard."
  }
}

variable "protected_arns" {
  description = "Exact ARNs, or ARN patterns, of other projects' resources whose names do not carry a protected name, such as a role or a CloudFront distribution ID. Both apply roles are refused them."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for arn in var.protected_arns : can(regex("^arn:[a-z-]+:[a-z0-9-]+:", arn))])
    error_message = "Each protected ARN must name its service; IAM refuses a wildcard service (arn:aws:*:...)."
  }
}