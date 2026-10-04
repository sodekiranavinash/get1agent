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
        Sid    = "ObjectAccess"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:GetObjectAttributes",
        ]
        Resource = [for arn in var.s3_bucket_arns : "${arn}/*"]
      },
    ]
  })
}

resource "aws_iam_role_policy" "s3_vectors_access" {
  count = length(var.s3_vector_bucket_arns) > 0 ? 1 : 0
  name  = "${var.name}-s3-vectors-access"
  role  = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "Vectors"
      Effect = "Allow"
      Action = [
        "s3vectors:CreateIndex",
        "s3vectors:DeleteIndex",
        "s3vectors:GetIndex",
        "s3vectors:ListIndexes",
        "s3vectors:PutVectors",
        "s3vectors:GetVectors",
        "s3vectors:DeleteVectors",
        "s3vectors:ListVectors",
        "s3vectors:QueryVectors",
      ]
      Resource = concat(
        var.s3_vector_bucket_arns,
        [for arn in var.s3_vector_bucket_arns : "${arn}/index/*"],
      )
    }]
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

resource "aws_iam_role_policy" "bedrock_rerank" {
  count = length(var.bedrock_rerank_arns) > 0 ? 1 : 0
  name  = "${var.name}-bedrock-rerank"
  role  = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "RerankModels"
      Effect   = "Allow"
      Action   = ["bedrock:Rerank"]
      Resource = var.bedrock_rerank_arns
    }]
  })
}

resource "aws_iam_role_policy" "bedrock_guardrail_management" {
  count = var.enable_guardrail_management ? 1 : 0
  name  = "${var.name}-bedrock-guardrail-management"
  role  = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Control plane: create/update/delete/list guardrails. Create and List
        # are region-scoped and cannot be narrowed to a guardrail ARN.
        Sid    = "ManageGuardrails"
        Effect = "Allow"
        Action = [
          "bedrock:CreateGuardrail",
          "bedrock:GetGuardrail",
          "bedrock:ListGuardrails",
          "bedrock:UpdateGuardrail",
          "bedrock:DeleteGuardrail",
          "bedrock:CreateGuardrailVersion",
          "bedrock:ListGuardrailVersions",
        ]
        Resource = "*"
      },
      {
        # Standalone checks (the workspace's guardrail tester).
        Sid      = "ApplyGuardrails"
        Effect   = "Allow"
        Action   = ["bedrock:ApplyGuardrail"]
        Resource = "arn:aws:bedrock:*:*:guardrail/*"
      },
    ]
  })
}

resource "aws_iam_role_policy" "lambda_invoke" {
  count = length(var.lambda_invoke_arns) > 0 ? 1 : 0
  name  = "${var.name}-lambda-invoke"
  role  = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "InvokeFunctions"
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = var.lambda_invoke_arns
    }]
  })
}

resource "aws_iam_role_policy" "bedrock_agentcore" {
  count = length(var.bedrock_agentcore_arns) > 0 ? 1 : 0
  name  = "${var.name}-bedrock-agentcore"
  role  = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CodeInterpreterSessions"
        Effect = "Allow"
        Action = [
          "bedrock-agentcore:StartCodeInterpreterSession",
          "bedrock-agentcore:InvokeCodeInterpreter",
          "bedrock-agentcore:StopCodeInterpreterSession",
          "bedrock-agentcore:GetCodeInterpreterSession",
        ]
        Resource = var.bedrock_agentcore_arns
      },
      {
        # AgentCore Identity: fetch a user's third-party OAuth token on demand.
        Sid    = "IdentityToken"
        Effect = "Allow"
        Action = [
          "bedrock-agentcore:GetResourceOauth2Token",
          "bedrock-agentcore:GetWorkloadAccessToken",
          "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
          "bedrock-agentcore:GetWorkloadAccessTokenForUserId",
        ]
        Resource = "*"
      },
      {
        # AgentCore Browser sessions + Registry records (Platform status). These
        # only apply where the matching resource ARNs are supplied, so listing
        # them for every module that passes bedrock_agentcore_arns is safe.
        Sid    = "BrowserAndRegistry"
        Effect = "Allow"
        Action = [
          "bedrock-agentcore:StartBrowserSession",
          "bedrock-agentcore:StopBrowserSession",
          "bedrock-agentcore:GetBrowserSession",
          "bedrock-agentcore:ListBrowserSessions",
          "bedrock-agentcore:ConnectBrowserAutomation",
          "bedrock-agentcore:CreateRegistryRecord",
          "bedrock-agentcore:GetRegistryRecord",
          "bedrock-agentcore:ListRegistryRecords",
          "bedrock-agentcore:SearchRegistryRecords",
        ]
        Resource = var.bedrock_agentcore_arns
      },
    ]
  })
}

resource "aws_iam_role_policy" "dynamodb_access" {
  count = length(var.dynamodb_table_arns) > 0 ? 1 : 0
  name  = "${var.name}-dynamodb-access"
  role  = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "TableAccess"
      Effect = "Allow"
      Action = [
        "dynamodb:GetItem",
        "dynamodb:BatchGetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:BatchWriteItem",
        "dynamodb:Query",
        "dynamodb:Scan",
        "dynamodb:DescribeTable",
      ]
      Resource = concat(
        var.dynamodb_table_arns,
        [for arn in var.dynamodb_table_arns : "${arn}/index/*"],
      )
    }]
  })
}

resource "aws_iam_role_policy" "kms_access" {
  count = length(var.kms_key_arns) > 0 ? 1 : 0
  name  = "${var.name}-kms-access"
  role  = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "EncryptDecrypt"
      Effect = "Allow"
      Action = [
        "kms:Encrypt",
        "kms:Decrypt",
        "kms:GenerateDataKey",
      ]
      Resource = var.kms_key_arns
    }]
  })
}

resource "aws_iam_role_policy" "xray" {
  count = var.tracing_mode == "Active" ? 1 : 0
  name  = "${var.name}-xray"
  role  = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "XRayWrite"
      Effect   = "Allow"
      Action   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
      Resource = "*"
    }]
  })
}
