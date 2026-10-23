output "read_policy_json" {
  description = "JSON IAM policy that allows reading Parameter Store under /portfolio/<env>/. Attached to pipeline roles by the iam module."
  value       = data.aws_iam_policy_document.read.json
}

output "parameter_path_prefix" {
  description = "Parameter Store path prefix for this environment, for example /portfolio/dev."
  value       = "/portfolio/${var.env}"
}
