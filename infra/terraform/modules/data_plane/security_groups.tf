resource "aws_security_group" "app" {
  name        = "${var.name_prefix}-app"
  description = "FastAPI app server (SSH admin + HTTP API)"
  vpc_id      = aws_vpc.main.id

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name_prefix}-app-sg"
  }
}

resource "aws_security_group_rule" "app_ssh" {
  type              = "ingress"
  security_group_id = aws_security_group.app.id
  description       = "SSH admin access (DBeaver tunnel, deploy debugging)"
  from_port         = 22
  to_port           = 22
  protocol          = "tcp"
  cidr_blocks       = var.allowed_ssh_cidr_blocks
}

resource "aws_security_group_rule" "app_http" {
  type              = "ingress"
  security_group_id = aws_security_group.app.id
  description       = "nginx HTTP (Cloudflare -> api subdomain)"
  from_port         = 80
  to_port           = 80
  protocol          = "tcp"
  cidr_blocks       = var.allowed_http_cidr_blocks
}

resource "aws_security_group_rule" "app_api" {
  count = length(var.allowed_api_cidr_blocks) > 0 ? 1 : 0

  type              = "ingress"
  security_group_id = aws_security_group.app.id
  description       = "Direct FastAPI access (optional; default is nginx-only)"
  from_port         = var.api_port
  to_port           = var.api_port
  protocol          = "tcp"
  cidr_blocks       = var.allowed_api_cidr_blocks
}

resource "aws_security_group" "postgres" {
  name        = "${var.name_prefix}-postgres"
  description = "PostgreSQL reachable only from the app EC2"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL from app server"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

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
}
