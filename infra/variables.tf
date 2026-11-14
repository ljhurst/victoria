variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "environment" {
  description = "Environment name (e.g., prod)"
  type        = string
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "bucket_name" {
  description = "S3 bucket holding the entire wiki"
  type        = string
  default     = "lj-victoria-wiki"
}

variable "mcp_lambda_package_path" {
  description = "Path to the zipped MCP Lambda package. Run `scripts/build_lambda.sh mcp`"
  type        = string
}

variable "viewer_lambda_package_path" {
  description = "Path to the zipped viewer Lambda package. Run `scripts/build_lambda.sh viewer`"
  type        = string
}

variable "lasso_issuer_url" {
  description = "Lasso's OIDC issuer URL — the authorization server Victoria verifies MCP bearer tokens against."
  type        = string
}

variable "anthropic_federation" {
  description = "Workload identity IDs from the Claude Console that let the MCP Lambda's role exchange an AWS-signed token for Anthropic access. Not secret."
  type = object({
    rule_id            = string
    organization_id    = string
    service_account_id = string
  })

  validation {
    condition     = can(regex("^fdrl_\\w+$", var.anthropic_federation.rule_id))
    error_message = "rule_id must be a federation rule ID (fdrl_...)."
  }

  validation {
    condition     = can(regex("^svac_\\w+$", var.anthropic_federation.service_account_id))
    error_message = "service_account_id must be a service account ID (svac_...)."
  }

  validation {
    condition     = can(regex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", var.anthropic_federation.organization_id))
    error_message = "organization_id must be the organization's UUID."
  }
}
