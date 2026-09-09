resource "aws_iam_role" "app" {
  name = "${var.name_prefix}-kong"

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

resource "aws_iam_role_policy_attachment" "app_ssm" {
  role       = aws_iam_role.app.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "app" {
  name = "${var.name_prefix}-kong"
  role = aws_iam_role.app.name
}

data "aws_ssm_parameter" "amazon_linux_2023_arm" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "app" {
  ami                    = data.aws_ssm_parameter.amazon_linux_2023_arm.value
  instance_type          = var.ec2_instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.app.id]
  iam_instance_profile   = aws_iam_instance_profile.app.name

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = 16
    encrypted   = true
  }

  user_data = templatefile("${path.module}/app_user_data.sh", {
    aws_region                  = data.aws_region.current.name
    api_hostname                = var.api_hostname
    kong_ui_hostname            = var.kong_ui_hostname
    kong_image                  = var.kong_image
    name_prefix                 = var.name_prefix
    db_credentials_secret_arn   = aws_secretsmanager_secret.db_credentials.arn
    kong_admin_secret_arn       = aws_secretsmanager_secret.kong_admin_credentials.arn
    db_host                     = aws_db_instance.postgres.address
    db_name                     = var.db_name
    db_master_username          = var.db_username
    db_iam_username             = var.db_iam_username
    kong_db_name                = var.kong_db_name
    kong_db_iam_username        = var.kong_db_iam_username
    bootstrap_db_script         = file("${path.module}/bootstrap-db.sh")
    deploy_kong_script          = file("${path.module}/deploy-kong.sh.tpl")
    bootstrap_kong_admin_script = file("${path.module}/bootstrap-kong-admin.sh")
  })

  tags = {
    Name = "${var.name_prefix}-kong"
  }

  lifecycle {
    ignore_changes = [key_name]
  }

  depends_on = [
    aws_secretsmanager_secret_version.db_credentials,
    aws_secretsmanager_secret_version.kong_admin_credentials,
    aws_db_instance.postgres,
  ]
}

data "aws_region" "current" {}

resource "aws_eip" "app" {
  domain = "vpc"

  tags = {
    Name = "${var.name_prefix}-kong-eip"
  }
}

resource "aws_eip_association" "app" {
  instance_id   = aws_instance.app.id
  allocation_id = aws_eip.app.id
}
