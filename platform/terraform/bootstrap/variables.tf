variable "region" {
  description = "AWS region for the Terraform state bucket and its KMS key. Must match the region in the environment backend files."
  type        = string
  default     = "us-east-1"
}
