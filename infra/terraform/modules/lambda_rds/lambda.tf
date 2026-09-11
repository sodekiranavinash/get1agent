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
  handler          = var.handler
  runtime          = var.runtime
  architectures    = var.architectures
  memory_size      = var.memory_size
  timeout          = var.timeout
  layers           = var.layer_arns

  environment {
    variables = var.environment
  }

  dynamic "vpc_config" {
    for_each = length(var.subnet_ids) > 0 ? [1] : []
    content {
      subnet_ids         = var.subnet_ids
      security_group_ids = [aws_security_group.lambda[0].id]
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy_attachment.logs,
    aws_iam_role_policy_attachment.vpc,
    aws_iam_role_policy.rds_connect,
    aws_iam_role_policy.ssm_read,
    aws_iam_role_policy.s3_access,
    aws_iam_role_policy.sqs_access,
    aws_iam_role_policy.step_functions_access,
    aws_iam_role_policy.bedrock_access,
    aws_security_group_rule.postgres_from_lambda,
  ]

  lifecycle {
    ignore_changes = [
      filename,
      source_code_hash,
    ]
  }

  tags = var.tags
}

resource "aws_lambda_event_source_mapping" "sqs" {
  count = var.enable_event_source_mapping ? 1 : 0

  event_source_arn                   = var.event_source_queue_arn
  function_name                      = aws_lambda_function.this.arn
  batch_size                         = var.event_source_batch_size
  function_response_types            = ["ReportBatchItemFailures"]
  maximum_batching_window_in_seconds = 0
}
