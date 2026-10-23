variable "env" {
  description = "Environment name. Must be dev or live. Used in the repository name."
  type        = string

  validation {
    condition     = contains(["dev", "live"], var.env)
    error_message = "The env variable must be either \"dev\" or \"live\"."
  }
}
