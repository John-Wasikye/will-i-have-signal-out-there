data "aws_partition" "current" {}

data "aws_region" "current" {}

data "aws_caller_identity" "current" {}

locals {
  # The session_box module gives the instance the same name, and the scheduler role is
  # limited to instances with this Name tag.
  name       = "portfolio-${var.env}-session-box"
  partition  = data.aws_partition.current.partition
  region     = data.aws_region.current.name
  account_id = data.aws_caller_identity.current.account_id
}

# --- The role the box itself uses -------------------------------------------------------------

data "aws_iam_policy_document" "ec2_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "box" {
  name               = local.name
  description        = "Role for the ${var.env} session box."
  assume_role_policy = data.aws_iam_policy_document.ec2_trust.json
}

resource "aws_iam_instance_profile" "box" {
  name = local.name
  role = aws_iam_role.box.name
}

# Session Manager lets me open a shell on the box from the browser, so no SSH port is open.
resource "aws_iam_role_policy_attachment" "session_manager" {
  role       = aws_iam_role.box.name
  policy_arn = "arn:${local.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "data_access" {
  name   = "data-access"
  role   = aws_iam_role.box.id
  policy = var.data_access_policy_json
}

resource "aws_iam_role_policy" "parameters" {
  name   = "parameter-store-read"
  role   = aws_iam_role.box.id
  policy = var.parameter_read_policy_json
}

# The box publishes gold Parquet files and status.json to the site bucket. It can write and
# read them but not delete them.
data "aws_iam_policy_document" "site_publish" {
  statement {
    sid       = "ListSiteBucket"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [var.site_bucket_arn]
  }

  statement {
    sid       = "PublishFiles"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${var.site_bucket_arn}/*"]
  }
}

resource "aws_iam_role_policy" "site_publish" {
  name   = "site-publish"
  role   = aws_iam_role.box.id
  policy = data.aws_iam_policy_document.site_publish.json

  lifecycle {
    # Guards against giving a dev box the live site bucket, or the reverse.
    precondition {
      condition     = strcontains(var.site_bucket_arn, "portfolio-${var.env}-site-")
      error_message = "The site bucket ARN must belong to the same environment as the env variable."
    }
  }
}

# --- The role the scheduler uses to start and stop the box ----------------------------------

data "aws_iam_policy_document" "scheduler_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }

    # Stops another account from using the scheduler to reach this role.
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${local.name}-scheduler"
  description        = "Lets EventBridge Scheduler start and stop the ${var.env} session box."
  assume_role_policy = data.aws_iam_policy_document.scheduler_trust.json
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    sid       = "StartAndStopTheSessionBox"
    effect    = "Allow"
    actions   = ["ec2:StartInstances", "ec2:StopInstances"]
    resources = ["arn:${local.partition}:ec2:${local.region}:${local.account_id}:instance/*"]

    condition {
      test     = "StringEquals"
      variable = "ec2:ResourceTag/Name"
      values   = [local.name]
    }
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "start-and-stop-session-box"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}
