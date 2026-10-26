# Everything for the MCP server Lambda — the endpoint Claude connects to (via
# porto). Read/write on the wiki bucket, the Anthropic key, its own role and
# log group. Mirrors viewer.tf.

locals {
  mcp_domain        = "victoria-mcp.bylukehurst.com"
  mcp_function_name = "lj-victoria-mcp"
}

resource "aws_iam_role" "mcp_lambda" {
  name                 = "victoria-lambda"
  assume_role_policy   = data.aws_iam_policy_document.lambda_assume_role.json
  permissions_boundary = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/stych/victoria-boundary"
}

data "aws_iam_policy_document" "mcp_lambda_permissions" {
  statement {
    sid       = "WikiBucketReadWrite"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.wiki.arn, "${aws_s3_bucket.wiki.arn}/*"]
  }

  statement {
    sid       = "ReadAnthropicApiKey"
    effect    = "Allow"
    actions   = ["ssm:GetParameter"]
    resources = ["${local.ssm_param_arn_prefix}${local.anthropic_api_key_ssm_param}"]
  }

  statement {
    sid       = "CloudWatchLogs"
    effect    = "Allow"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:*:*:log-group:/aws/lambda/${local.mcp_function_name}*"]
  }
}

resource "aws_iam_role_policy" "mcp_lambda" {
  name   = "victoria-lambda-permissions"
  role   = aws_iam_role.mcp_lambda.id
  policy = data.aws_iam_policy_document.mcp_lambda_permissions.json
}

resource "aws_lambda_function" "mcp" {
  function_name = local.mcp_function_name
  role          = aws_iam_role.mcp_lambda.arn

  filename         = var.mcp_lambda_package_path
  source_code_hash = filebase64sha256(var.mcp_lambda_package_path)

  handler       = "victoria.lambda_handler.handler"
  runtime       = "python3.13"
  architectures = ["arm64"]

  memory_size = 512
  timeout     = 120 # generous headroom for consolidate's multi-turn tool loop (DESIGN §10)

  environment {
    variables = {
      WIKI_BUCKET                   = aws_s3_bucket.wiki.bucket
      LASSO_ISSUER_URL              = var.lasso_issuer_url
      VICTORIA_RESOURCE_URL         = "https://${local.mcp_domain}/"
      VICTORIA_RESOURCE_URL_ALIASES = var.legacy_resource_server_url
      ANTHROPIC_API_KEY_SSM_PARAM   = local.anthropic_api_key_ssm_param
      POWERTOOLS_SERVICE_NAME       = "victoria-mcp"
    }
  }
}

resource "aws_lambda_function_url" "mcp" {
  function_name      = aws_lambda_function.mcp.function_name
  authorization_type = "NONE"
  invoke_mode        = "BUFFERED" # no streaming in v1 (DESIGN §11)
}

resource "aws_cloudwatch_log_group" "mcp" {
  name              = "/aws/lambda/${aws_lambda_function.mcp.function_name}"
  retention_in_days = 30
}

module "mcp_front" {
  source = "git::https://github.com/ljhurst/stych.git//infra/modules/function-url-site?ref=v1.5.0"

  domain_name    = local.mcp_domain
  function_url   = aws_lambda_function_url.mcp.function_url
  origin_timeout = aws_lambda_function.mcp.timeout
}
