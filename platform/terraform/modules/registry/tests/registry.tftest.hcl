# Plan-only tests with a mock AWS provider. No AWS calls are made.
# Run from the module folder: terraform init -backend=false, then terraform test.

mock_provider "aws" {}

run "images_are_scanned_when_they_are_pushed" {
  command = plan

  variables {
    env = "dev"
  }

  assert {
    condition     = aws_ecr_repository.airflow.image_scanning_configuration[0].scan_on_push == true
    error_message = "Every pushed image must be scanned."
  }
}

run "a_pushed_tag_can_never_be_overwritten" {
  command = plan

  variables {
    env = "dev"
  }

  assert {
    condition     = aws_ecr_repository.airflow.image_tag_mutability == "IMMUTABLE"
    error_message = "Tags must be immutable, so a version always means the same image."
  }
}

run "images_are_encrypted_at_rest" {
  command = plan

  variables {
    env = "dev"
  }

  assert {
    condition     = aws_ecr_repository.airflow.encryption_configuration[0].encryption_type == "AES256"
    error_message = "Images must be encrypted at rest."
  }
}

run "the_repository_is_named_for_the_environment" {
  command = plan

  variables {
    env = "live"
  }

  assert {
    condition     = aws_ecr_repository.airflow.name == "portfolio-live-airflow"
    error_message = "The repository must be named portfolio-<env>-airflow."
  }
}

run "old_images_are_cleaned_up" {
  command = plan

  variables {
    env = "dev"
  }

  assert {
    condition     = length([for r in jsondecode(aws_ecr_lifecycle_policy.airflow.policy).rules : r if r.selection.tagStatus == "untagged" && r.selection.countNumber == 7 && r.selection.countUnit == "days"]) == 1
    error_message = "Untagged images must expire after 7 days."
  }

  assert {
    condition     = length([for r in jsondecode(aws_ecr_lifecycle_policy.airflow.policy).rules : r if r.selection.tagStatus == "any" && r.selection.countType == "imageCountMoreThan" && r.selection.countNumber == 10]) == 1
    error_message = "Only the newest 10 images must be kept."
  }
}

run "dev_repository_can_be_deleted_with_its_images" {
  command = plan

  variables {
    env = "dev"
  }

  assert {
    condition     = aws_ecr_repository.airflow.force_delete == true
    error_message = "A dev repository must be removable with its images, so teardown stays cheap."
  }
}

run "live_repository_cannot_be_deleted_while_it_holds_images" {
  command = plan

  variables {
    env = "live"
  }

  assert {
    condition     = aws_ecr_repository.airflow.force_delete == false
    error_message = "A live repository must not be removable while it holds images."
  }
}

run "rejects_an_unknown_environment" {
  command = plan

  variables {
    env = "staging"
  }

  expect_failures = [
    var.env,
  ]
}
