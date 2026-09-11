resource "aws_instance" "jumpbox" {
  ami                         = data.aws_ssm_parameter.amazon_linux_2023.value
  instance_type               = var.ec2_instance_type
  subnet_id                   = aws_subnet.public.id
  vpc_security_group_ids      = [aws_security_group.jumpbox.id]
  iam_instance_profile        = aws_iam_instance_profile.jumpbox.name
  associate_public_ip_address = true

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = var.ec2_root_volume_gb
    encrypted   = true
  }

  tags = {
    Name = "${var.name_prefix}-jumpbox"
  }

  lifecycle {
    create_before_destroy = true
    # The subnet already assigns a public IP; keep the existing instance rather
    # than replacing it on attribute drift.
    ignore_changes = [key_name, ami, associate_public_ip_address]
  }

  depends_on = [
    aws_security_group_rule.postgres_from_jumpbox,
  ]
}

data "aws_ssm_parameter" "amazon_linux_2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

data "aws_region" "current" {}
