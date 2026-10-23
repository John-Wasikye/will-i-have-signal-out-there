variable "env" {
  description = "Environment name. Must be dev or live. Used in every resource name and tag."
  type        = string

  validation {
    condition     = contains(["dev", "live"], var.env)
    error_message = "The env variable must be either \"dev\" or \"live\"."
  }
}

variable "instance_type" {
  description = "Session box size. t4g.2xlarge for everyday work, m7g.2xlarge for heavy batch jobs."
  type        = string
  default     = "t4g.2xlarge"

  validation {
    condition     = contains(["t4g.2xlarge", "m7g.2xlarge"], var.instance_type)
    error_message = "The instance_type must be t4g.2xlarge or m7g.2xlarge."
  }
}

variable "ami_id" {
  description = "An arm64 Amazon Machine Image. Check its manifest before the first use."
  type        = string
}

variable "subnet_id" {
  description = "Subnet the box starts in. A public subnet, because there is no NAT gateway."
  type        = string
}

variable "security_group_ids" {
  description = "Security groups for the box. Allow no inbound traffic from the internet."
  type        = list(string)
  default     = []
}

variable "instance_profile_name" {
  description = "Instance profile that gives the box read access to Parameter Store and write access to its buckets."
  type        = string
}

variable "schedule_enabled" {
  description = "Whether the box starts by itself every night. I turn it off in dev, so only the live box runs nightly. The hard stop stays on either way."
  type        = bool
  default     = true
}

variable "scheduler_role_arn" {
  description = "Role that EventBridge Scheduler assumes to start and stop the box. It needs ec2:StartInstances and ec2:StopInstances on this box only."
  type        = string
}

variable "root_volume_gb" {
  description = "Size of the root disk in GB. It holds the operating system and the k3s data, not the project data."
  type        = number
  default     = 50
}

variable "idle_cpu_percent" {
  description = "Average CPU use below which the box counts as idle. The value is a placeholder until I measure it (OQ-P02)."
  type        = number
  default     = 5
}

variable "idle_evaluation_periods" {
  description = "Number of 5-minute periods the box must stay idle before it stops. The value is a placeholder until I measure it (OQ-P02)."
  type        = number
  default     = 6
}
