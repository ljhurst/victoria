# Everything for the MCP server Lambda — the endpoint Claude connects to (via
# porto). Read/write on the wiki bucket, the Anthropic key, its own role and
# log group. Mirrors viewer.tf.

resource "aws_ssm_parameter" "anthropic_api_key" {
  name  = "/victoria/anthropic-api-key"
  type  = "SecureString"
  value = "REPLACE_ME_MANUALLY"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_iam_role" "mcp_lambda" {
  name               = "victoria-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
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
    resources = [aws_ssm_parameter.anthropic_api_key.arn]
  }

  statement {
    sid       = "CloudWatchLogs"
    effect    = "Allow"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:*:*:log-group:/aws/lambda/${aws_lambda_function.mcp.function_name}*"]
  }
}

resource "aws_iam_role_policy" "mcp_lambda" {
  name   = "victoria-lambda-permissions"
  role   = aws_iam_role.mcp_lambda.id
  policy = data.aws_iam_policy_document.mcp_lambda_permissions.json
}

resource "aws_lambda_function" "mcp" {
  function_name = "lj-victoria-mcp"
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
      WIKI_BUCKET                 = aws_s3_bucket.wiki.bucket
      LASSO_ISSUER_URL            = var.lasso_issuer_url
      VICTORIA_RESOURCE_URL       = var.resource_server_url
      ANTHROPIC_API_KEY_SSM_PARAM = aws_ssm_parameter.anthropic_api_key.name
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
