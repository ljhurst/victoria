output "wiki_bucket" {
  value = aws_s3_bucket.wiki.bucket
}

output "mcp_server_url" {
  description = "Add this as the URL when adding Victoria as a custom connector in Claude mobile app (DESIGN §5)."
  value       = aws_lambda_function_url.mcp.function_url
}

output "viewer_url" {
  description = "The wiki viewer's address; the Function URL is only the CloudFront origin."
  value       = "https://${local.viewer_domain}/"
}

output "viewer_cname_target" {
  description = "Point a DNS-only CNAME for victoria-viewer in Cloudflare at this hostname"
  value       = module.viewer_front.cname_target
}

output "mcp_cname_target" {
  description = "Point a DNS-only CNAME for victoria-mcp in Cloudflare at this hostname"
  value       = module.mcp_front.cname_target
}
