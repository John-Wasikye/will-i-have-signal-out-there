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

  # Only this distribution can read the site bucket.
  site_distribution_arn = module.site.distribution_arn
  alarm_actions         = [module.alerts.topic_arn]
}

# Dev has no nightly schedule, so no pipeline is watched for a missed run. A run I start by
# hand still emails me when it fails.
module "alerts" {
  source = "../../modules/alerts"

  env          = local.env
  alert_emails = var.alert_emails
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

module "box_iam" {
  source = "../../modules/box_iam"

  env                        = local.env
  site_bucket_arn            = module.storage.bucket_arns["site"]
  data_access_policy_json    = module.iam.data_access_policy_json
  parameter_read_policy_json = module.parameters.read_policy_json
  registry_arn               = module.registry.repository_arn
  alert_policy_json          = module.alerts.publish_policy_json
}

module "session_box" {
  source = "../../modules/session_box"

  env                   = local.env
  ami_id                = var.box_ami_id
  subnet_id             = var.box_subnet_id
  security_group_ids    = var.box_security_group_ids
  instance_profile_name = module.box_iam.instance_profile_name
  scheduler_role_arn    = module.box_iam.scheduler_role_arn
  schedule_enabled      = false
}

module "site" {
  source = "../../modules/site"

  env                         = local.env
  bucket_regional_domain_name = module.storage.bucket_regional_domain_names["site"]
}

module "serving" {
  source = "../../modules/serving"

  env               = local.env
  published_bucket  = module.storage.bucket_names["site"]
  lambda_zip_path   = var.lambda_zip_path
  lambda_zip_sha256 = var.lambda_zip_sha256
  allowed_origins   = ["https://${module.site.domain_name}"]
}

module "registry" {
  source = "../../modules/registry"

  env = local.env
}
