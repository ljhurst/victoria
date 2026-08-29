output "wiki_bucket" {
  value = aws_s3_bucket.wiki.bucket
}

output "mcp_server_url" {
  description = "Add this as the URL when adding Victoria as a custom connector in Claude mobile app (DESIGN §5)."
  value       = aws_lambda_function_url.mcp.function_url
}

output "viewer_url" {
  description = "The wiki viewer's Function URL. Set this as `viewer_base_url` in terraform.tfvars and re-apply, and register `<url>auth/callback` as a redirect URI for the `victoria-viewer` client in Lasso."
  value       = aws_lambda_function_url.viewer.function_url
}
