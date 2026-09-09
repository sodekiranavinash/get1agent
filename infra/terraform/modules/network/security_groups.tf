resource "aws_security_group" "jumpbox" {
  name        = "${var.name_prefix}-jumpbox"
  description = "On-demand jumpbox: SSM from laptop, egress to RDS only (no inbound ports)"
  vpc_id      = aws_vpc.main.id

  egress {
    description = "SSM and package updates (public IP only while instance is running)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name_prefix}-jumpbox-sg"
  }

  lifecycle {
    create_before_destroy = true
    ignore_changes        = [description]
  }
}

resource "aws_security_group" "postgres" {
  name        = "${var.name_prefix}-postgres"
  description = "PostgreSQL reachable from jumpbox EC2 and VPC Lambdas"
  vpc_id      = aws_vpc.main.id

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name_prefix}-postgres-sg"
  }

  lifecycle {
    create_before_destroy = true
    ignore_changes        = [description]
  }
}

resource "aws_security_group_rule" "postgres_from_jumpbox" {
  type                     = "ingress"
  security_group_id        = aws_security_group.postgres.id
  source_security_group_id = aws_security_group.jumpbox.id
  description              = "PostgreSQL from jumpbox"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
}
