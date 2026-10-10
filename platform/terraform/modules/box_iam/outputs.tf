output "instance_profile_name" {
  description = "Instance profile for the session box. Pass it to the session_box module."
  value       = aws_iam_instance_profile.box.name
}

output "scheduler_role_arn" {
  description = "Role that EventBridge Scheduler assumes to start and stop the box. Pass it to the session_box module."
  value       = aws_iam_role.scheduler.arn
}
