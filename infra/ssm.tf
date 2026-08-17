# SSM Parameter Store over Secrets Manager (DESIGN §5, §12): free tier vs.
# per-secret cost. Values are set out-of-band (AWS console/CLI), never
# through Terraform state (DESIGN §12, §16) — these resources only reserve
# the parameter names/paths and the KMS-encrypted type; `aws ssm put-parameter
# --overwrite` sets the actual values manually after apply.

resource "aws_ssm_parameter" "anthropic_api_key" {
  name  = "/victoria/anthropic-api-key"
  type  = "SecureString"
  value = "REPLACE_ME_MANUALLY"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "mcp_auth_token" {
  name  = "/victoria/mcp-auth-token"
  type  = "SecureString"
  value = "REPLACE_ME_MANUALLY"

  lifecycle {
    ignore_changes = [value]
  }
}
