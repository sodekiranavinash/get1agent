# IMPORTANT: never change `name` — AWS rejects duplicate SG names and destroys block on dependents.
resource "aws_security_group" "app" {
  name                   = "${var.name_prefix}-kong"
  description            = "Kong API Gateway (HTTP proxy on :80)"
  vpc_id                 = aws_vpc.main.id
  revoke_rules_on_delete = true

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name_prefix}-kong-sg"
  }

  lifecycle {
    create_before_destroy = true
    ignore_changes        = [description]
  }

  timeouts {
    delete = "15m"
  }
}

resource "aws_security_group_rule" "app_http" {
  type              = "ingress"
  security_group_id = aws_security_group.app.id
  description       = "Kong proxy HTTP (Cloudflare)"
  from_port         = 80
  to_port           = 80
  protocol          = "tcp"
  cidr_blocks       = local.allowed_http_ipv4_cidr_blocks
  ipv6_cidr_blocks  = local.cloudflare_ipv6_cidrs
}

# IMPORTANT: never change `name` or `description` — both force SG replacement.
resource "aws_security_group" "postgres" {
  name                   = "${var.name_prefix}-postgres"
  description            = "PostgreSQL reachable only from the app EC2"
  vpc_id                 = aws_vpc.main.id
  revoke_rules_on_delete = true

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

  timeouts {
    delete = "15m"
  }
}

resource "aws_security_group_rule" "postgres_from_app" {
  type                     = "ingress"
  security_group_id        = aws_security_group.postgres.id
  source_security_group_id = aws_security_group.app.id
  description              = "PostgreSQL from app server"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"

  lifecycle {
    create_before_destroy = true
  }
}
