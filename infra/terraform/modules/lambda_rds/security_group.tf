resource "aws_security_group" "lambda" {
  name_prefix = "${var.name}-"
  description = "Lambda VPC access to RDS for ${var.name}"
  vpc_id      = var.vpc_id

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
  type                     = "ingress"
  security_group_id        = var.postgres_security_group_id
  source_security_group_id = aws_security_group.lambda.id
  description              = "PostgreSQL from ${var.name}"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
}
