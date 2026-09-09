resource "aws_iam_role_policy" "jumpbox_bootstrap_db" {
  name = "${var.name_prefix}-jumpbox-bootstrap-db"
  role = aws_iam_role.jumpbox.id

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
      ]
    }]
  })
}
