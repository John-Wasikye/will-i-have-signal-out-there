output "topic_arn" {
  description = "ARN of the run alerts topic. The install script takes it as ALERT_TOPIC_ARN."
  value       = local.topic_arn
}

output "publish_policy_json" {
  description = "Policy that lets the box send run alerts and record good runs. Pass it to the box_iam module."
  value       = data.aws_iam_policy_document.publish.json
}
