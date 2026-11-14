aws_region   = "us-east-1"
environment  = "prod"
project_name = "victoria"

mcp_lambda_package_path    = "../agent/dist/victoria-mcp.zip"
viewer_lambda_package_path = "../agent/dist/victoria-viewer.zip"

lasso_issuer_url = "https://lasso.bylukehurst.com/"

# Settings > Workload identity in the Claude Console
anthropic_federation = {
  rule_id            = "fdrl_01BE9DvqYSJ9eiyR3KPCTXGk"
  organization_id    = "7eff1b18-ebc4-4ba7-95f9-7b55fcb7356e"
  service_account_id = "svac_0167gDwEKWjBXM46HcT7CwPt"
}
