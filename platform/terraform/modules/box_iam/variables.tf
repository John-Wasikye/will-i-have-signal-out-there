variable "env" {
  description = "Environment name. Must be dev or live. The box role can reach only this environment's resources."
  type        = string

  validation {
    condition     = contains(["dev", "live"], var.env)
    error_message = "The env variable must be either \"dev\" or \"live\"."
  }
}

variable "site_bucket_arn" {
  description = "ARN of this environment's site bucket. The box publishes the Parquet files and status.json here."
  type        = string
}

variable "data_access_policy_json" {
  description = "Bucket and Glue access policy, from the data_access_policy_json output of the iam module."
  type        = string
}

variable "parameter_read_policy_json" {
  description = "Parameter Store read policy, from the parameters module."
  type        = string
}

variable "registry_arn" {
  description = "ARN of this environment's image repository, from the registry module. The box pulls the Airflow image from it."
  type        = string
}
