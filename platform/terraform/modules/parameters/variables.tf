variable "env" {
  description = "Environment name. Must be dev or live. Parameters under /portfolio/<env>/ are readable."
  type        = string

  validation {
    condition     = contains(["dev", "live"], var.env)
    error_message = "The env variable must be either \"dev\" or \"live\"."
  }
}
