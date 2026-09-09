data "aws_rds_engine_version" "postgres" {
  engine  = "postgres"
  version = var.postgres_engine_version
  latest  = true
}

resource "random_password" "db_master" {
  length  = 32
  special = false
}

resource "aws_ssm_parameter" "db_credentials" {
  name        = "/${var.name_prefix}/postgres/credentials"
  description = "Master PostgreSQL credentials (SecureString)"
  type        = "SecureString"
  value = jsonencode({
    username = var.db_username
    password = random_password.db_master.result
    dbname   = var.db_name
    engine   = "postgres"
    port     = 5432
    purpose  = "admin-only"
  })

  tags = {
    Name = "${var.name_prefix}-postgres-credentials"
  }
}

resource "aws_db_instance" "postgres" {
  identifier = "${var.name_prefix}-postgres"

  engine         = "postgres"
  engine_version = data.aws_rds_engine_version.postgres.version
  instance_class = var.db_instance_class

  db_name  = var.db_name
  username = var.db_username
  password = random_password.db_master.result

  allocated_storage     = var.allocated_storage_gb
  max_allocated_storage = 0
  storage_type          = "gp3"
  storage_encrypted     = true

  db_subnet_group_name   = aws_db_subnet_group.postgres.name
  vpc_security_group_ids = [aws_security_group.postgres.id]

  iam_database_authentication_enabled = true

  multi_az                = false
  publicly_accessible     = false
  skip_final_snapshot     = true
  deletion_protection     = false
  backup_retention_period = var.backup_retention_days

  performance_insights_enabled = false
  auto_minor_version_upgrade   = true
  copy_tags_to_snapshot        = true

  tags = {
    Name = "${var.name_prefix}-postgres"
  }

  lifecycle {
    # AWS cannot rename subnet groups in-place; identifier rename is optional/slow.
    ignore_changes = [db_subnet_group_name, identifier]
  }
}

resource "aws_ssm_parameter" "db_connection" {
  name        = "/${var.name_prefix}/postgres/connection"
  description = "PostgreSQL connection details (master user + password)"
  type        = "SecureString"
  value = jsonencode({
    host     = aws_db_instance.postgres.address
    port     = aws_db_instance.postgres.port
    dbname   = var.db_name
    username = var.db_username
    password = random_password.db_master.result
    sslmode  = "require"
    iam_user = var.db_iam_username
    note     = "RDS is private; reach from jumpbox EC2 or VPC Lambdas only"
  })

  tags = {
    Name = "${var.name_prefix}-postgres-connection"
  }
}
