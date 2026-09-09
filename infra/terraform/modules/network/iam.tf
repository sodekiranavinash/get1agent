data "aws_caller_identity" "current" {}

resource "aws_iam_role" "jumpbox" {
  name = "${var.name_prefix}-jumpbox"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "jumpbox_ssm" {
  role       = aws_iam_role.jumpbox.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "jumpbox_db_bootstrap" {
  name = "${var.name_prefix}-jumpbox-db-bootstrap"
  role = aws_iam_role.jumpbox.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "ReadPostgresSsmParams"
      Effect = "Allow"
      Action = [
        "ssm:GetParameter",
        "ssm:GetParameters",
      ]
      Resource = "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter/${var.name_prefix}/postgres/*"
    }]
  })
}

resource "aws_iam_instance_profile" "jumpbox" {
  name = "${var.name_prefix}-jumpbox"
  role = aws_iam_role.jumpbox.name
}
