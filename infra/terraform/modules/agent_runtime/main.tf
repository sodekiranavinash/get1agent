terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.21"
    }
  }
}

# --- Container image ---------------------------------------------------------

resource "aws_ecr_repository" "worker" {
  name                 = var.ecr_repository_name
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

# --- Runtime execution role --------------------------------------------------

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

resource "aws_iam_role" "runtime" {
  name = "${var.name}-runtime"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "bedrock-agentcore.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "runtime" {
  name = "${var.name}-runtime"
  role = aws_iam_role.runtime.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Dynamo"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:BatchGetItem",
          "dynamodb:Query",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:BatchWriteItem",
        ]
        Resource = concat(var.dynamodb_table_arns, [for arn in var.dynamodb_table_arns : "${arn}/index/*"])
      },
      {
        Sid      = "S3"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
        Resource = concat(var.s3_bucket_arns, [for arn in var.s3_bucket_arns : "${arn}/*"])
      },
      {
        Sid    = "S3Vectors"
        Effect = "Allow"
        Action = [
          "s3vectors:CreateIndex",
          "s3vectors:GetIndex",
          "s3vectors:ListIndexes",
          "s3vectors:PutVectors",
          "s3vectors:GetVectors",
          "s3vectors:DeleteVectors",
          "s3vectors:QueryVectors",
        ]
        Resource = concat(
          var.s3_vector_bucket_arns,
          [for arn in var.s3_vector_bucket_arns : "${arn}/index/*"],
        )
      },
      {
        Sid      = "InvokeMcp"
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        Resource = var.mcp_function_arns
      },
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:*"
      },
      {
        Sid      = "XRay"
        Effect   = "Allow"
        Action   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
        Resource = "*"
      },
      {
        Sid      = "EcrAuth"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Sid    = "EcrPull"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
        ]
        Resource = aws_ecr_repository.worker.arn
      },
    ]
  })
}

# --- AgentCore Runtime -------------------------------------------------------

resource "aws_bedrockagentcore_agent_runtime" "worker" {
  # The runtime needs a pushed image; deploy the ECR repo first (targeted apply),
  # push the ARM64 image, then apply again with `agent_worker_image_uri` set.
  count = var.container_image_uri == "" ? 0 : 1

  # AgentCore runtime names allow only letters, digits and underscores.
  agent_runtime_name = replace(var.name, "-", "_")
  description        = "get1agent agent worker (Strands on AgentCore Runtime)"
  role_arn           = aws_iam_role.runtime.arn

  agent_runtime_artifact {
    container_configuration {
      container_uri = var.container_image_uri
    }
  }

  network_configuration {
    network_mode = "PUBLIC"
  }

  protocol_configuration {
    server_protocol = "HTTP"
  }

  environment_variables = var.runtime_environment

  authorizer_configuration {
    custom_jwt_authorizer {
      discovery_url    = var.jwt_discovery_url
      allowed_audience = var.jwt_allowed_audience
    }
  }

  request_header_configuration {
    request_header_allowlist = ["Authorization"]
  }

  lifecycle_configuration {
    idle_runtime_session_timeout = var.idle_timeout_seconds
    max_lifetime                 = var.max_lifetime_seconds
  }

  tags = var.tags
}

# --- Streaming proxy Lambda (Function URL) -----------------------------------

resource "aws_iam_role" "proxy" {
  name = "${var.name}-proxy"

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

resource "aws_iam_role_policy_attachment" "proxy_logs" {
  role       = aws_iam_role.proxy.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "proxy" {
  count = var.container_image_uri == "" ? 0 : 1

  function_name    = "${var.name}-run"
  role             = aws_iam_role.proxy.arn
  filename         = var.proxy_zip
  source_code_hash = filebase64sha256(var.proxy_zip)
  handler          = "handler.lambda_handler"
  runtime          = var.python_runtime
  architectures    = ["arm64"]
  timeout          = var.proxy_timeout_seconds
  memory_size      = 256

  environment {
    variables = {
      AGENT_RUNTIME_ARN         = aws_bedrockagentcore_agent_runtime.worker[0].agent_runtime_arn
      AGENT_RUNTIME_QUALIFIER   = "DEFAULT"
      AGENT_RUN_TIMEOUT_SECONDS = tostring(var.proxy_timeout_seconds - 5)
      # The proxy verifies the Auth0 token before invoking the runtime, so an
      # unauthenticated request never starts a session.
      AUTH0_DISCOVERY_URL = var.jwt_discovery_url
      AUTH0_AUDIENCE      = join(",", var.jwt_allowed_audience)
    }
  }

  tags = var.tags
}

resource "aws_lambda_function_url" "proxy" {
  count = var.container_image_uri == "" ? 0 : 1

  function_name      = aws_lambda_function.proxy[0].function_name
  authorization_type = "NONE"
  invoke_mode        = "RESPONSE_STREAM"

  cors {
    allow_origins = var.allowed_origins
    allow_methods = ["POST"]
    allow_headers = ["authorization", "content-type", "x-agent-session"]
    max_age       = 3600
  }
}

resource "aws_lambda_permission" "proxy_public" {
  count = var.container_image_uri == "" ? 0 : 1

  statement_id           = "AllowPublicFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.proxy[0].function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}
