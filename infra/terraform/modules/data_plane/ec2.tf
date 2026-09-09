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

resource "aws_iam_instance_profile" "jumpbox" {
  name = "${var.name_prefix}-jumpbox"
  role = aws_iam_role.jumpbox.name
}

data "aws_ssm_parameter" "amazon_linux_2023_arm" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "jumpbox" {
  ami                    = data.aws_ssm_parameter.amazon_linux_2023_arm.value
  instance_type          = var.ec2_instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.jumpbox.id]
  iam_instance_profile   = aws_iam_instance_profile.jumpbox.name

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = var.ec2_root_volume_gb
    encrypted   = true
  }

  user_data = templatefile("${path.module}/app_user_data.sh", {
    aws_region                = data.aws_region.current.name
    db_credentials_secret_arn = aws_secretsmanager_secret.db_credentials.arn
    db_host                   = aws_db_instance.postgres.address
    db_name                   = var.db_name
    db_master_username        = var.db_username
    db_iam_username           = var.db_iam_username
    bootstrap_db_script       = file("${path.module}/bootstrap-db.sh")
  })

  tags = {
    Name = "${var.name_prefix}-jumpbox"
  }

  lifecycle {
    ignore_changes = [key_name]
  }

  depends_on = [
    aws_secretsmanager_secret_version.db_credentials,
    aws_db_instance.postgres,
    aws_security_group_rule.postgres_from_jumpbox,
  ]
}

data "aws_region" "current" {}
