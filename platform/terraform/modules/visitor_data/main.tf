terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Visitor counts and events for the portfolio site, one table per environment.
# Provisioned capacity of 5 read and 5 write units keeps the table inside the free tier.
# Heavy traffic is throttled rather than billed (design doc section 12.5).
resource "aws_dynamodb_table" "visitor" {
  name           = "portfolio-${var.env}-visitor"
  billing_mode   = "PROVISIONED"
  read_capacity  = 5
  write_capacity = 5
  hash_key       = "pk"
  range_key      = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  # Live visitor data cannot be dropped by a single accidental destroy. Dev tables can.
  deletion_protection_enabled = var.env == "live"
}
