# Everything for the wiki viewer Lambda — a read-only browser for the wiki,
# behind Lasso OAuth. Read-only on the wiki bucket, its own session secret,
# role and log group. Mirrors mcp.tf.

resource "aws_ssm_parameter" "viewer_session_secret" {
  name  = "/victoria/viewer-session-secret"
  type  = "SecureString"
  value = "REPLACE_ME_MANUALLY"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_iam_role" "viewer_lambda" {
  name               = "victoria-viewer-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

data "aws_iam_policy_document" "viewer_lambda_permissions" {
  statement {
    sid       = "WikiBucketReadOnly"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.wiki.arn, "${aws_s3_bucket.wiki.arn}/*"]
  }

  statement {
    sid       = "ReadViewerSessionSecret"
    effect    = "Allow"
    actions   = ["ssm:GetParameter"]
    resources = [aws_ssm_parameter.viewer_session_secret.arn]
  }

  statement {
    sid       = "CloudWatchLogs"
    effect    = "Allow"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:*:*:log-group:/aws/lambda/${aws_lambda_function.viewer.function_name}*"]
  }
}

resource "aws_iam_role_policy" "viewer_lambda" {
  name   = "victoria-viewer-lambda-permissions"
  role   = aws_iam_role.viewer_lambda.id
  policy = data.aws_iam_policy_document.viewer_lambda_permissions.json
}

resource "aws_lambda_function" "viewer" {
  function_name = "lj-victoria-viewer"
  role          = aws_iam_role.viewer_lambda.arn

  filename         = var.viewer_lambda_package_path
  source_code_hash = filebase64sha256(var.viewer_lambda_package_path)

  handler       = "victoria.viewer.lambda_handler.handler"
  runtime       = "python3.13"
  architectures = ["arm64"]

  memory_size = 512
  timeout     = 30

  environment {
    variables = {
      WIKI_BUCKET                     = aws_s3_bucket.wiki.bucket
      LASSO_ISSUER_URL                = var.lasso_issuer_url
      VIEWER_BASE_URL                 = var.viewer_base_url
      VIEWER_SESSION_SECRET_SSM_PARAM = aws_ssm_parameter.viewer_session_secret.name
      LASSO_CLIENT_ID                 = "victoria-viewer"
    }
  }
}

resource "aws_lambda_function_url" "viewer" {
  function_name      = aws_lambda_function.viewer.function_name
  authorization_type = "NONE" # the app runs its own Lasso OAuth check
  invoke_mode        = "BUFFERED"
}

resource "aws_cloudwatch_log_group" "viewer" {
  name              = "/aws/lambda/${aws_lambda_function.viewer.function_name}"
  retention_in_days = 30
}
