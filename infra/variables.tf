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

variable "lambda_package_path" {
  description = "Path to the zipped Lambda deployment package. Run `agent/scripts/build_lambda.sh`"
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
