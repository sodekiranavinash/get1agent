locals {
  name = "${var.name_prefix}-ingestion"
}

resource "aws_sqs_queue" "dlq" {
  name                      = "${local.name}-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true

  tags = var.tags
}

resource "aws_sqs_queue" "this" {
  name                       = "${local.name}-docs"
  visibility_timeout_seconds = var.visibility_timeout_seconds
  message_retention_seconds  = 345600
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.max_receive_count
  })

  tags = var.tags
}

resource "aws_sqs_queue_policy" "this" {
  queue_url = aws_sqs_queue.this.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowEventBridge"
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.this.arn
      Condition = {
        ArnEquals = { "aws:SourceArn" = aws_cloudwatch_event_rule.s3.arn }
      }
    }]
  })
}

resource "aws_cloudwatch_event_rule" "s3" {
  name        = "${local.name}-s3-object-created"
  description = "Route knowledge base uploads to the ingestion queue"

  event_pattern = jsonencode({
    source        = ["aws.s3"]
    "detail-type" = ["Object Created"]
    detail = {
      bucket = { name = [var.bucket_name] }
    }
  })

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "queue" {
  rule      = aws_cloudwatch_event_rule.s3.name
  target_id = "ingestion-queue"
  arn       = aws_sqs_queue.this.arn
}

resource "aws_cloudwatch_log_group" "sfn" {
  name              = "/aws/vendedlogs/states/${local.name}"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

resource "aws_iam_role" "sfn" {
  name = "${local.name}-sfn"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "states.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "sfn" {
  name = "${local.name}-sfn"
  role = aws_iam_role.sfn.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokeStages"
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = [
          var.extract_function_arn,
          var.index_function_arn,
          var.mark_failed_function_arn,
        ]
      },
      {
        Sid    = "Logging"
        Effect = "Allow"
        Action = [
          "logs:CreateLogDelivery",
          "logs:GetLogDelivery",
          "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery",
          "logs:ListLogDeliveries",
          "logs:PutResourcePolicy",
          "logs:DescribeResourcePolicies",
          "logs:DescribeLogGroups",
        ]
        Resource = "*"
      },
    ]
  })
}

resource "aws_sfn_state_machine" "this" {
  name     = local.name
  type     = "EXPRESS"
  role_arn = aws_iam_role.sfn.arn

  definition = templatefile("${path.module}/statemachine.asl.json", {
    extract_function_arn     = var.extract_function_arn
    index_function_arn       = var.index_function_arn
    mark_failed_function_arn = var.mark_failed_function_arn
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn.arn}:*"
    include_execution_data = false
    level                  = "ERROR"
  }

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "dlq" {
  alarm_name          = "${local.name}-dlq-not-empty"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  dimensions          = { QueueName = aws_sqs_queue.dlq.name }
  treat_missing_data  = "notBreaching"

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "failed" {
  alarm_name          = "${local.name}-executions-failed"
  namespace           = "AWS/States"
  metric_name         = "ExecutionsFailed"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  dimensions          = { StateMachineArn = aws_sfn_state_machine.this.arn }
  treat_missing_data  = "notBreaching"

  tags = var.tags
}
