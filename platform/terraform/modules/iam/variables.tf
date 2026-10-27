variable "env" {
  description = "Environment name. Must be dev or live. Live roles trust only the main branch. Dev roles trust any ref in the repository."
  type        = string

  validation {
    condition     = contains(["dev", "live"], var.env)
    error_message = "The env variable must be either \"dev\" or \"live\"."
  }
}

variable "github_repo" {
  description = "GitHub repository allowed to assume the pipeline roles, as owner@owner_id/name@repo_id, the form GitHub puts in its tokens."
  type        = string
  default     = "John-Wasikye@171445038/will-i-have-signal-out-there@1412828974"

  # GitHub signs this repository's tokens with the permanent owner and repository IDs, so a
  # trust written as plain owner/name never matches.
  validation {
    condition     = can(regex("^[^/@]+@[0-9]+/[^/@]+@[0-9]+$", var.github_repo))
    error_message = "The github_repo variable must look like owner@owner_id/name@repo_id."
  }
}

variable "pipeline_names" {
  description = "Names of the pipelines that each get a role, for example platform_skeleton. Role names become portfolio-<env>-<name>."
  type        = list(string)
  default     = ["platform_skeleton"]

  validation {
    condition     = length(var.pipeline_names) > 0 && alltrue([for name in var.pipeline_names : can(regex("^[a-z0-9_]+$", name))])
    error_message = "Each pipeline name must use lowercase letters, digits and underscores, and the list cannot be empty."
  }
}

variable "raw_bucket_arn" {
  description = "ARN of this environment's raw bucket."
  type        = string
}

variable "lake_bucket_arn" {
  description = "ARN of this environment's lake bucket."
  type        = string
}

variable "glue_database_name" {
  description = "Name of this environment's Glue database, portfolio_dev or portfolio_live."
  type        = string
}

variable "parameter_read_policy_json" {
  description = "JSON policy that allows reading Parameter Store under /portfolio/<env>/*. Built by the parameters module."
  type        = string
}

variable "create_oidc_provider" {
  description = "Whether this configuration creates the GitHub OIDC provider. Only one environment per AWS account should set this to true."
  type        = bool
  default     = true
}
