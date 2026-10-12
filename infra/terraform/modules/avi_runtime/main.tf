terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.21"
    }
  }
}

# ---------------------------------------------------------------------------
# Avi's MicroVM runtime.
#
# Avi streams from a Lambda MicroVM rather than an API Gateway integration for two
# reasons: an HTTP API cannot stream and caps an integration at 30 s, and a Lambda
# Function is capped at 15 minutes. The image is built by Lambda from a Dockerfile
# artifact, which pulls the Avi agent container from ECR (built and pushed by
# `infra/aws/deploy-avi.sh`) and adds the Node streaming proxy on port 8080.
#
# The guest path is deliberately *not* here: it is a plain Lambda with a
# RESPONSE_STREAM Function URL, registered in backend/registry.json as
# `avi-guest`, because a guest needs no session and no MicroVM.
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# --- Container image -------------------------------------------------------

resource "aws_ecr_repository" "agent" {
  name                 = var.ecr_repository_name
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

# Keep image storage bounded: Avi's image is large (the agent framework), so a
# small retention window matters more here than for the agent runtime.
resource "aws_ecr_lifecycle_policy" "agent" {
  repository = aws_ecr_repository.agent.name

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
        description  = "Keep only the 3 most recent tagged images"
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

# --- Build role ------------------------------------------------------------

resource "aws_iam_role" "build" {
  count = var.enabled ? 1 : 0

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

resource "aws_iam_role_policy" "build" {
  count = var.enabled ? 1 : 0

  name = "${var.name}-microvm-build"
  role = aws_iam_role.build[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadArtifact"
        Effect = "Allow"
        Action = ["s3:GetObject"]
        # The whole content-addressed prefix, not one hash-specific key: a rebuilt
        # artifact changes the object key, and an exact-key policy applied after
        # the build started would fail it with "Access denied".
        Resource = "arn:aws:s3:::${var.artifact_bucket}/${replace(var.microvm_artifact_key, "/[^/]+$/", "*")}"
      },
      {
        Sid      = "PullAgentImage"
        Effect   = "Allow"
        Action   = ["ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage", "ecr:BatchCheckLayerAvailability"]
        Resource = aws_ecr_repository.agent.arn
      },
      {
        Sid      = "PullAgentImageAuth"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
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
  count = var.enabled ? 1 : 0

  bucket      = var.artifact_bucket
  key         = var.microvm_artifact_key
  source      = var.microvm_zip
  source_hash = filebase64sha256(var.microvm_zip)
}

# --- MicroVM image ---------------------------------------------------------

resource "aws_lambdamicrovms_image" "avi" {
  count = var.enabled ? 1 : 0

  name           = "${var.name}-avi"
  base_image_arn = "arn:aws:lambda:${data.aws_region.current.region}:aws:microvm-image:al2023-1"
  build_role_arn = aws_iam_role.build[0].arn

  code_artifact {
    uri = "s3://${var.artifact_bucket}/${var.microvm_artifact_key}"
  }

  cpu_configuration {
    architecture = "ARM_64"
  }

  # Everything the agent container needs. The reserved `AWS_REGION` is left alone;
  # the Bedrock region is passed under its own key because the corpus, the models
  # and the S3 Vectors index all live in ap-south-1.
  environment_variables = {
    AVI_MODE = "prod"
    AVI_PORT = "8000"
    PORT     = "8080"

    AVI_SCOPE      = var.scope_user_id
    AVI_KB_ID      = var.kb_id
    AVI_REGION     = data.aws_region.current.region
    BEDROCK_REGION = var.bedrock_region

    AVI_ALLOWED_ORIGINS = join(",", var.allowed_origins)

    # Identity: the agent verifies the HMAC on the session token the control plane
    # minted. Without this the service refuses to resolve a caller at all.
    AVI_SESSION_SECRET = var.session_secret

    # Guest turns are rate-limited per IP hash; the salt keeps the hash stable
    # without storing an IP.
    AVI_GUEST_SALT = var.guest_salt

    AVI_TELEMETRY = "emf"
  }

  tags = var.tags

  depends_on = [aws_s3_object.microvm_artifact, aws_iam_role_policy.build]

  timeouts {
    create = "30m"
  }
}

# --- Runtime role (what the agent container may reach) ---------------------

resource "aws_iam_role" "runtime" {
  name = "${var.name}-avi-runtime"

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

resource "aws_iam_role_policy" "runtime" {
  name = "${var.name}-avi-runtime"
  role = aws_iam_role.runtime.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ModelCalls"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
          "bedrock:Converse",
          "bedrock:ConverseStream",
          "bedrock:ApplyGuardrail",
        ]
        # Cross-region inference profiles resolve to several regions, so the
        # wildcard is required for the global Nova profile.
        Resource = "*"
      },
      {
        Sid      = "DataPlane"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:BatchGetItem"]
        Resource = [var.table_arn, "${var.table_arn}/index/*"]
      },
      {
        Sid      = "Objects"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
        Resource = [var.bucket_arn, "${var.bucket_arn}/*"]
      },
      {
        Sid      = "Vectors"
        Effect   = "Allow"
        Action   = ["s3vectors:QueryVectors", "s3vectors:GetVectors", "s3vectors:ListVectors", "s3vectors:PutVectors"]
        Resource = "*"
      },
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:*"
      },
      {
        Sid      = "Tracing"
        Effect   = "Allow"
        Action   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
        Resource = "*"
      },
    ]
  })
}
