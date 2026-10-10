locals {
  env = "live"

  tags = {
    Project     = "will-i-have-signal-out-there"
    Environment = local.env
    ManagedBy   = "terraform"
  }
}

module "storage" {
  source = "../../modules/storage"

  env              = local.env
  size_alarm_bytes = var.size_alarm_bytes
  alarm_actions    = var.alarm_actions
}

module "catalog" {
  source = "../../modules/catalog"

  env = local.env
}

module "visitor_data" {
  source = "../../modules/visitor_data"

  env = local.env
}

module "parameters" {
  source = "../../modules/parameters"

  env = local.env
}

module "iam" {
  source = "../../modules/iam"

  env                        = local.env
  github_repo                = var.github_repo
  pipeline_names             = var.pipeline_names
  raw_bucket_arn             = module.storage.bucket_arns["raw"]
  lake_bucket_arn            = module.storage.bucket_arns["lake"]
  glue_database_name         = module.catalog.database_name
  parameter_read_policy_json = module.parameters.read_policy_json

  # This configuration creates the GitHub OIDC provider. envs/dev relies on it, so apply this
  # configuration before envs/dev the first time.
  create_oidc_provider = true
}

# The budget is account-wide, so it is created only from the live configuration.
module "budget" {
  source = "../../modules/budget"

  limit_usd    = var.budget_limit_usd
  alert_emails = var.alert_emails
}
