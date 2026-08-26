locals {
  function_name = var.name
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_lambda_function" "this" {
  function_name    = local.function_name
  role             = aws_iam_role.lambda.arn
  filename         = var.filename
  source_code_hash = var.source_code_hash
  handler          = "bootstrap"
  runtime          = "provided.al2023"
  architectures    = var.architectures
  memory_size      = var.memory_size
  timeout          = var.timeout

  environment {
    variables = var.environment
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy_attachment.logs,
  ]

  # Zip updates come from the per-tool GitHub Actions deploy, not from terraform apply.
  lifecycle {
    ignore_changes = [
      filename,
      source_code_hash,
    ]
  }

  tags = var.tags
}

resource "aws_lambda_permission" "invoke" {
  count         = var.allowed_invoke_principal == "" ? 0 : 1
  statement_id  = "AllowInvokeFromGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  principal     = var.allowed_invoke_principal
}
