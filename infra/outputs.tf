output "wiki_bucket" {
  value = aws_s3_bucket.wiki.bucket
}

output "mcp_server_url" {
  description = "Add this as the URL when adding Victoria as a custom connector in Claude mobile app (DESIGN §5)."
  value       = aws_lambda_function_url.victoria.function_url
}
