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
  description = "S3 bucket holding the entire wiki (DESIGN §3, §4)."
  type        = string
  default     = "lj-victoria-wiki"
}

variable "lambda_package_path" {
  description = "Path to the zipped Lambda deployment package. Run `agent/scripts/build_lambda.sh`"
  type        = string
}
