resource "aws_lambda_function" "victoria" {
  function_name = "lj-victoria-mcp"
  role          = aws_iam_role.lambda.arn

  filename         = var.lambda_package_path
  source_code_hash = filebase64sha256(var.lambda_package_path)

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

resource "aws_lambda_function_url" "victoria" {
  function_name      = aws_lambda_function.victoria.function_name
  authorization_type = "NONE"
  invoke_mode        = "BUFFERED" # no streaming in v1 (DESIGN §11)
}

resource "aws_cloudwatch_log_group" "victoria" {
  name              = "/aws/lambda/${aws_lambda_function.victoria.function_name}"
  retention_in_days = 30
}
