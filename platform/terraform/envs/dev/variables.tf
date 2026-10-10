variable "region" {
  description = "AWS region for the dev environment."
  type        = string
  default     = "us-east-1"
}

variable "github_repo" {
  description = "GitHub repository allowed to assume the dev pipeline roles, in owner/name form."
  type        = string
  default     = "John-Wasikye/will-i-have-signal-out-there"
}

variable "pipeline_names" {
  description = "Pipelines that each get a dev role, for example platform_skeleton."
  type        = list(string)
  default     = ["platform_skeleton"]
}

variable "size_alarm_bytes" {
  description = "Bucket size in bytes that raises the size alarm on each dev bucket. The default is 100 GB."
  type        = number
  default     = 107374182400
}

variable "box_ami_id" {
  description = "An arm64 image for the session box. I check its manifest before the first use."
  type        = string
}

variable "box_subnet_id" {
  description = "A public subnet for the session box. There is no NAT gateway."
  type        = string
}

variable "box_security_group_ids" {
  description = "Security groups for the session box. They allow no inbound traffic from the internet."
  type        = list(string)
  default     = []
}

variable "lambda_zip_path" {
  description = "Path to the API package built by platform/serving/build_package.py."
  type        = string
  default     = "../../../serving/build/function.zip"
}

variable "lambda_zip_sha256" {
  description = "Base64 SHA-256 of the API package. The build script prints it."
  type        = string
}
