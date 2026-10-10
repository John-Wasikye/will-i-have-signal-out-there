variable "env" {
  description = "Environment name. Must be dev or live. Used in every resource name."
  type        = string

  validation {
    condition     = contains(["dev", "live"], var.env)
    error_message = "The env variable must be either \"dev\" or \"live\"."
  }
}

variable "bucket_regional_domain_name" {
  description = "Regional domain name of the site bucket, from the bucket_regional_domain_names output of the storage module."
  type        = string
}
