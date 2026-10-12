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

  tracing_config {
    mode = var.tracing_mode
  }

  # No vpc_config: every Lambda in this design runs outside a VPC.

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy_attachment.logs,
    aws_iam_role_policy.s3_access,
    aws_iam_role_policy.s3_vectors_access,
    aws_iam_role_policy.sqs_access,
    aws_iam_role_policy.step_functions_access,
    aws_iam_role_policy.bedrock_access,
    aws_iam_role_policy.bedrock_rerank,
    aws_iam_role_policy.bedrock_agentcore,
    aws_iam_role_policy.dynamodb_access,
    aws_iam_role_policy.kms_access,
    aws_iam_role_policy.lambda_invoke,
    aws_iam_role_policy.xray,
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

# --- optional streaming Function URL -----------------------------------------
# See the variables: this exists for response streaming, not as a general-purpose
# ingress. Avi's guest path is the only caller.

resource "aws_lambda_function_url" "this" {
  count = var.create_function_url ? 1 : 0

  function_name      = aws_lambda_function.this.function_name
  authorization_type = var.function_url_auth_type
  invoke_mode        = var.function_url_invoke_mode

  dynamic "cors" {
    for_each = length(var.function_url_cors_origins) > 0 ? [1] : []
    content {
      allow_credentials = false
      allow_origins     = var.function_url_cors_origins
      allow_methods     = ["POST"]
      allow_headers     = ["content-type"]
      max_age           = 3600
    }
  }

  depends_on = [aws_lambda_function.this]
}

resource "aws_lambda_permission" "function_url_public" {
  count = var.create_function_url && var.function_url_auth_type == "NONE" ? 1 : 0

  statement_id           = "AllowPublicFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.this.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}
