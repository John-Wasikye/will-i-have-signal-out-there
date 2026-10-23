terraform {
  required_version = ">= 1.10"

  # The state file lives outside the repository. Its path is given at init (see main.tf),
  # because the -state flag is deprecated.
  backend "local" {}

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
