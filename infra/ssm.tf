# Secret values are written out of band and never managed here:
# Terraform refreshes every attribute into state, including decrypted values.
locals {
  viewer_session_secret_ssm_param = "/victoria/viewer-session-secret"

  ssm_param_arn_prefix = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter"
}

data "aws_caller_identity" "current" {}
