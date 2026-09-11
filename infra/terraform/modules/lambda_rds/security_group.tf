resource "aws_security_group" "lambda" {
  count = var.vpc_id == "" ? 0 : 1

  name_prefix = "${var.name}-"
  description = "Lambda VPC access for ${var.name}"
  vpc_id      = var.vpc_id

  egress {
    description = "HTTPS to AWS services via VPC endpoints (no NAT in this VPC)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description     = "PostgreSQL to RDS"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.postgres_security_group_id]
  }

  tags = merge(var.tags, {
    Name = "${var.name}-lambda-sg"
  })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group_rule" "postgres_from_lambda" {
  count = var.vpc_id == "" ? 0 : 1

  type                     = "ingress"
  security_group_id        = var.postgres_security_group_id
  source_security_group_id = aws_security_group.lambda[0].id
  description              = "PostgreSQL from ${var.name}"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
}
