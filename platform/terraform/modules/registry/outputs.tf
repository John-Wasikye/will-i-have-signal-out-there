output "repository_url" {
  description = "Address of the repository, for example 123456789012.dkr.ecr.us-east-1.amazonaws.com/portfolio-dev-airflow. The install script takes it as IMAGE_REPOSITORY."
  value       = aws_ecr_repository.airflow.repository_url
}

output "repository_arn" {
  description = "ARN of the repository, for permission policies."
  value       = aws_ecr_repository.airflow.arn
}
