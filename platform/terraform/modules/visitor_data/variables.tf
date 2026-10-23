variable "env" {
  description = "Environment name. Must be dev or live. The table is named portfolio-<env>-visitor."
  type        = string

  validation {
    condition     = contains(["dev", "live"], var.env)
    error_message = "The env variable must be either \"dev\" or \"live\"."
  }
}
