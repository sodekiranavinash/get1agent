resource "aws_iam_role_policy" "app_runtime" {
  name = "${var.name_prefix}-app-runtime"
  role = aws_iam_role.app.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "PullApiImage"
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
        ]
        Resource = "*"
      },
      {
        Sid    = "ConnectToPostgresWithIam"
        Effect = "Allow"
        Action = [
          "rds-db:connect",
        ]
        Resource = "arn:aws:rds-db:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:dbuser:${aws_db_instance.postgres.resource_id}/${var.db_iam_username}"
      },
    ]
  })
}

resource "aws_iam_role_policy" "app_bootstrap_db" {
  name = "${var.name_prefix}-app-bootstrap-db"
  role = aws_iam_role.app.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "ReadMasterDbSecretForIamUserBootstrap"
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue",
      ]
      Resource = [
        aws_secretsmanager_secret.db_credentials.arn,
      ]
    }]
  })
}

data "aws_caller_identity" "current" {}
