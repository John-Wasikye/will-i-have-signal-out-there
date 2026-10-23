variable "env" {
  description = "Environment name. Must be dev or live. Used in every resource name."
  type        = string

  validation {
    condition     = contains(["dev", "live"], var.env)
    error_message = "The env variable must be either \"dev\" or \"live\"."
  }
}

variable "published_bucket" {
  description = "Name of this environment's site bucket. The function reads the Parquet files under its published/ folder."
  type        = string
}

variable "lambda_zip_path" {
  description = "Path to the zip file that holds the FastAPI app, its dependencies built for arm64, and handler.py."
  type        = string
}

variable "lambda_zip_sha256" {
  description = "Base64 SHA-256 of the zip file. A change in the file changes this value, which tells Terraform to update the function."
  type        = string
}

variable "allowed_origins" {
  description = "Websites that may call the API from a browser. A wildcard is not allowed."
  type        = list(string)

  validation {
    condition     = length(var.allowed_origins) > 0 && !contains(var.allowed_origins, "*")
    error_message = "List at least one origin, and do not use a wildcard."
  }
}

variable "memory_mb" {
  description = "Memory for the function in MB. DuckDB needs room to read Parquet files."
  type        = number
  default     = 1024
}

variable "timeout_seconds" {
  description = "Longest time a request may run. The page warns that a cold start can take up to 10 seconds."
  type        = number
  default     = 30
}

variable "reserved_concurrency" {
  description = "Most copies of the function that may run at once. It caps the cost of a traffic spike. null sets no reservation: use it where the account's whole Lambda limit is 10, because AWS keeps at least 10 unreserved, and that limit is then the cap anyway."
  type        = number
  default     = 10
}

variable "throttle_rate" {
  description = "Steady requests per second that the API accepts."
  type        = number
  default     = 20
}

variable "throttle_burst" {
  description = "Largest burst of requests the API accepts at once."
  type        = number
  default     = 40
}
