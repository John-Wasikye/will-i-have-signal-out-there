output "role_arns" {
  description = "Map of pipeline name to pipeline role ARN."
  value       = { for name, role in aws_iam_role.pipeline : name => role.arn }
}

output "oidc_provider_arn" {
  description = "ARN of the GitHub OIDC provider that the pipeline roles trust."
  value       = local.oidc_provider_arn
}

output "github_subject" {
  description = "The GitHub token subject that the pipeline roles accept, for example repo:owner/name:ref:refs/heads/main."
  value       = local.github_subject
}

output "data_access_policy_json" {
  description = "The bucket and Glue access policy that every pipeline role gets. The session box role reuses it."
  value       = data.aws_iam_policy_document.data_access.json
}
