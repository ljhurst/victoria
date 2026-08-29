resource "aws_ssm_parameter" "anthropic_api_key" {
  name  = "/victoria/anthropic-api-key"
  type  = "SecureString"
  value = "REPLACE_ME_MANUALLY"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "viewer_session_secret" {
  name  = "/victoria/viewer-session-secret"
  type  = "SecureString"
  value = "REPLACE_ME_MANUALLY"

  lifecycle {
    ignore_changes = [value]
  }
}
