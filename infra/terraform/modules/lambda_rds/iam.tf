data "aws_caller_identity" "current" {}

resource "aws_iam_role" "lambda" {
  name = "${var.name}-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "logs" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "vpc" {
  count = var.vpc_id == "" ? 0 : 1

  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy" "rds_connect" {
  count = var.rds_resource_id == "" || var.db_iam_username == "" ? 0 : 1

  name = "${var.name}-rds-connect"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "RdsIamConnect"
      Effect   = "Allow"
      Action   = "rds-db:connect"
      Resource = "arn:aws:rds-db:${var.aws_region}:${data.aws_caller_identity.current.account_id}:dbuser:${var.rds_resource_id}/${var.db_iam_username}"
    }]
  })
}

resource "aws_iam_role_policy" "ssm_read" {
  count = length(var.ssm_parameter_names) > 0 ? 1 : 0
  name  = "${var.name}-ssm-read"
  role  = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadParameters"
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters"]
        Resource = [for name in var.ssm_parameter_names : "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter${name}"]
      },
      {
        Sid      = "DecryptParameters"
        Effect   = "Allow"
        Action   = ["kms:Decrypt", "kms:DescribeKey"]
        Resource = "*"
      },
    ]
  })
}

resource "aws_iam_role_policy" "s3_access" {
  count = length(var.s3_bucket_arns) > 0 ? 1 : 0
  name  = "${var.name}-s3-access"
  role  = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ListBuckets"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = var.s3_bucket_arns
      },
      {
        Sid      = "ObjectAccess"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = [for arn in var.s3_bucket_arns : "${arn}/*"]
      },
    ]
  })
}

resource "aws_iam_role_policy" "sqs_access" {
  count = length(var.sqs_queue_arns) > 0 ? 1 : 0
  name  = "${var.name}-sqs-access"
  role  = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "ConsumeQueues"
      Effect = "Allow"
      Action = [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes",
        "sqs:ChangeMessageVisibility",
      ]
      Resource = var.sqs_queue_arns
    }]
  })
}

resource "aws_iam_role_policy" "step_functions_access" {
  count = length(var.step_functions_arns) > 0 ? 1 : 0
  name  = "${var.name}-step-functions-access"
  role  = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "StartExecutions"
      Effect   = "Allow"
      Action   = ["states:StartExecution"]
      Resource = var.step_functions_arns
    }]
  })
}

resource "aws_iam_role_policy" "bedrock_access" {
  count = length(var.bedrock_model_arns) > 0 ? 1 : 0
  name  = "${var.name}-bedrock-access"
  role  = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "InvokeModels"
      Effect   = "Allow"
      Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
      Resource = var.bedrock_model_arns
    }]
  })
}
