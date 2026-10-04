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

# Keep image storage bounded: each deploy pushes a new tag, so retain only the
# few most recent tagged worker images and drop untagged build layers quickly.
resource "aws_ecr_lifecycle_policy" "worker" {
  repository = aws_ecr_repository.worker.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 2 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 2
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep only the 3 most recent tagged worker images"
        selection = {
          tagStatus      = "tagged"
          tagPatternList = ["*"]
          countType      = "imageCountMoreThan"
          countNumber    = 3
        }
        action = { type = "expire" }
      },
    ]
  })
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
        # Decrypt a user's Vault provider secret when it is the run's model.
        Sid      = "VaultKms"
        Effect   = "Allow"
        Action   = ["kms:Decrypt", "kms:DescribeKey"]
        Resource = var.kms_key_arns
      },
      {
        # The platform model gateway is Amazon Bedrock (Converse / InvokeModel).
        Sid    = "BedrockModels"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
        ]
        Resource = var.bedrock_model_arns
      },
      {
        # Applying a Bedrock guardrail on a model call needs bedrock:ApplyGuardrail
        # for the guardrail (the workspace's, or one the user created in-app).
        Sid    = "BedrockGuardrails"
        Effect = "Allow"
        Action = [
          "bedrock:ApplyGuardrail",
          "bedrock:GetGuardrail",
        ]
        Resource = "arn:aws:bedrock:*:*:guardrail/*"
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
        # AgentCore Memory (short + long term) and Policy (tool-call decisions).
        Sid    = "BedrockAgentCoreMemoryPolicy"
        Effect = "Allow"
        Action = [
          "bedrock-agentcore:CreateEvent",
          "bedrock-agentcore:ListEvents",
          "bedrock-agentcore:GetEvent",
          "bedrock-agentcore:RetrieveMemoryRecords",
          "bedrock-agentcore:ListMemoryRecords",
          "bedrock-agentcore:GetMemoryRecord",
          "bedrock-agentcore:DeleteMemoryRecord",
          "bedrock-agentcore:GetMemory",
          "bedrock-agentcore:GetMemoryStrategy",
          "bedrock-agentcore:AuthorizeAction",
          "bedrock-agentcore:EvaluatePolicy",
        ]
        Resource = "*"
      },
      {
        # AgentCore Identity: fetch a user's third-party OAuth token on demand.
        Sid    = "BedrockAgentCoreIdentity"
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

# --- Control-plane Lambda (API Gateway) --------------------------------------
#
# Thin, gateway-authenticated endpoint (`POST /v1/agent-run/session`) that
# launches a Lambda MicroVM and mints its ingress token.

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
  handler          = var.proxy_handler
  runtime          = var.proxy_runtime
  architectures    = ["arm64"]
  timeout          = var.proxy_timeout_seconds
  memory_size      = 256

  environment {
    variables = {
      # Invoked by API Gateway behind the Auth0 JWT authorizer; the Lambda only
      # launches a MicroVM from this image, mints its ingress token, and returns
      # the endpoint to the browser.
      AGENT_MICROVM_IMAGE_ARN         = try(aws_lambdamicrovms_image.agent_run[0].arn, "")
      AGENT_MICROVM_TOKEN_TTL_MINUTES = "25"
      # The MicroVM outlives a single run (which is aborted at
      # `microvm_max_run_seconds`) so the stream is never cut by the platform.
      AGENT_MICROVM_MAX_DURATION_SECONDS = tostring(var.microvm_max_run_seconds + 300)
    }
  }

  tags = var.tags
}

resource "aws_iam_role_policy" "proxy_microvm" {
  name = "${var.name}-proxy-microvm"
  role = aws_iam_role.proxy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "MicrovmSession"
        Effect = "Allow"
        Action = [
          # Lambda MicroVM IAM actions live in the `lambda:` namespace.
          "lambda:RunMicrovm",
          "lambda:GetMicrovm",
          "lambda:CreateMicrovmAuthToken",
          # RunMicrovm depends on this to attach the ingress/egress network
          # connectors (the platform passes the default connectors even when the
          # caller specifies none). No execution role is passed, so iam:PassRole
          # is not required.
          "lambda:PassNetworkConnector",
        ]
        Resource = "*"
      },
    ]
  })
}

# --- Lambda MicroVM (long-running streaming proxy) ---------------------------
#
# A Lambda Function is capped at 15 minutes, so the streaming proxy runs in a
# Lambda MicroVM instead: it serves a dedicated HTTPS endpoint for up to 8 hours
# and can suspend/resume when idle. The control-plane Lambda above mints the
# MicroVM ingress auth token and hands the endpoint to the browser.

resource "aws_iam_role" "microvm_build" {
  count = var.container_image_uri == "" ? 0 : 1

  name = "${var.name}-microvm-build"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = ["sts:AssumeRole", "sts:TagSession"]
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "microvm_build" {
  count = var.container_image_uri == "" ? 0 : 1

  name = "${var.name}-microvm-build"
  role = aws_iam_role.microvm_build[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadArtifact"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "arn:aws:s3:::${var.artifact_bucket}/${var.microvm_artifact_key}"
      },
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:*"
      },
    ]
  })
}

resource "aws_s3_object" "microvm_artifact" {
  count = var.container_image_uri == "" ? 0 : 1

  bucket      = var.artifact_bucket
  key         = var.microvm_artifact_key
  source      = var.microvm_zip
  source_hash = filebase64sha256(var.microvm_zip)
}

resource "aws_lambdamicrovms_image" "agent_run" {
  count = var.container_image_uri == "" ? 0 : 1

  name           = "${var.name}-agent-run"
  base_image_arn = "arn:aws:lambda:${data.aws_region.current.region}:aws:microvm-image:al2023-1"
  build_role_arn = aws_iam_role.microvm_build[0].arn

  code_artifact {
    uri = "s3://${var.artifact_bucket}/${var.microvm_artifact_key}"
  }

  cpu_configuration {
    architecture = "ARM_64"
  }

  environment_variables = {
    AGENT_RUNTIME_ARN         = aws_bedrockagentcore_agent_runtime.worker[0].agent_runtime_arn
    AGENT_RUNTIME_QUALIFIER   = "DEFAULT"
    AGENT_RUN_TIMEOUT_SECONDS = tostring(var.microvm_max_run_seconds)
    AUTH_DISCOVERY_URL        = var.jwt_discovery_url
    AUTH_AUDIENCE             = join(",", var.jwt_allowed_audience)
    AGENT_RUN_ALLOWED_ORIGINS = join(",", var.allowed_origins)
    # AWS_REGION / AWS_DEFAULT_REGION are reserved (Lambda injects them), so the
    # region is passed under our own key and read with a fallback.
    AGENT_REGION = data.aws_region.current.region
  }

  tags = var.tags

  # The image build reads the zip from S3, so upload it first.
  depends_on = [aws_s3_object.microvm_artifact]

  # The caller content-addresses `microvm_artifact_key`, so a changed zip yields a
  # new `code_artifact.uri` and the provider applies it as a new image version in
  # place. (A forced replace would collide on the stable image name.)
  timeouts {
    create = "20m"
  }
}
