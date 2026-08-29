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

variable "viewer_base_url" {
  description = "The viewer Lambda's own Function URL (see the `viewer_url` output). Set after the first apply; must match the redirect URI registered for the `victoria-viewer` client in Lasso."
  type        = string
}

variable "lasso_issuer_url" {
  description = "Lasso's OIDC issuer URL — the authorization server Victoria verifies MCP bearer tokens against."
  type        = string
}

variable "resource_server_url" {
  description = "Victoria's own OAuth resource identifier. Set to this Lambda's Function URL."
  type        = string
}
