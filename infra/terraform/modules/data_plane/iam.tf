resource "aws_iam_role_policy" "app_runtime" {
  name = "${var.name_prefix}-kong-runtime"
  role = aws_iam_role.app.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ConnectToPostgresWithIamKong"
        Effect = "Allow"
        Action = [
          "rds-db:connect",
        ]
        Resource = "arn:aws:rds-db:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:dbuser:${aws_db_instance.postgres.resource_id}/${var.kong_db_iam_username}"
      },
      {
        Sid    = "ConnectToPostgresWithIamApp"
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
  name = "${var.name_prefix}-kong-bootstrap-db"
  role = aws_iam_role.app.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "ReadDbSecretsForBootstrap"
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue",
      ]
      Resource = [
        aws_secretsmanager_secret.db_credentials.arn,
        aws_secretsmanager_secret.kong_admin_credentials.arn,
      ]
    }]
  })
}

data "aws_caller_identity" "current" {}
