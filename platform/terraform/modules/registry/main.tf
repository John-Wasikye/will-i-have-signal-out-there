locals {
  keep_newest_images   = 10
  untagged_expiry_days = 7
}

# Where the session box pulls the Airflow image from.
resource "aws_ecr_repository" "airflow" {
  name = "portfolio-${var.env}-airflow"

  # A version tag always means the same image. A new build gets a new tag.
  image_tag_mutability = "IMMUTABLE"

  # Dev can be torn down with its images. Live must be emptied by hand first.
  force_delete = var.env == "dev"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

# Without a clean-up rule, every build would stay and be billed for storage.
resource "aws_ecr_lifecycle_policy" "airflow" {
  repository = aws_ecr_repository.airflow.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after ${local.untagged_expiry_days} days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = local.untagged_expiry_days
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep only the newest ${local.keep_newest_images} images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = local.keep_newest_images
        }
        action = { type = "expire" }
      },
    ]
  })
}
