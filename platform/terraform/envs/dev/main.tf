locals {
  env = "dev"

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

  # envs/live creates the OIDC provider. Apply envs/live before envs/dev the first time.
  create_oidc_provider = false
}
