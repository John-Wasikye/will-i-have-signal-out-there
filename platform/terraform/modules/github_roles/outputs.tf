output "plan_role_arn" {
  description = "Role for terraform plan on pull requests. GitHub variable TF_PLAN_ROLE_ARN_<ENV>."
  value       = aws_iam_role.plan.arn
}

output "apply_role_arn" {
  description = "Role for terraform apply in the GitHub environment. Environment variable TF_APPLY_ROLE_ARN."
  value       = aws_iam_role.apply.arn
}

output "deploy_role_arn" {
  description = "Role for the site and image deploy in the GitHub environment. Environment variable DEPLOY_ROLE_ARN."
  value       = aws_iam_role.deploy.arn
}
