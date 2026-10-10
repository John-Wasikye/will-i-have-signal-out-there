terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# One Glue database per environment. Iceberg tables for the lake are registered here.
resource "aws_glue_catalog_database" "this" {
  name        = "portfolio_${var.env}"
  description = "Iceberg tables for the portfolio ${var.env} environment."
}
