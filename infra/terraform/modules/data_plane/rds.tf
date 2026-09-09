data "aws_rds_engine_version" "postgres" {
  engine  = "postgres"
  version = var.postgres_engine_version
  latest  = true
}

resource "random_password" "db_master" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "db_credentials" {
  name                    = "${var.name_prefix}/postgres-credentials"
  description             = "Master PostgreSQL credentials for DBeaver / SSM tunnel only"
  recovery_window_in_days = 7

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username = var.db_username
    password = random_password.db_master.result
    dbname   = var.db_name
    engine   = "postgres"
    port     = 5432
    purpose  = "dbeaver-and-admin-tunnel-only"
  })
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

resource "aws_secretsmanager_secret" "db_connection" {
  name                    = "${var.name_prefix}/postgres-connection"
  description             = "DBeaver connection details (master user + password)"
  recovery_window_in_days = 7

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_secretsmanager_secret_version" "db_connection" {
  secret_id = aws_secretsmanager_secret.db_connection.id
  secret_string = jsonencode({
    host         = aws_db_instance.postgres.address
    port         = aws_db_instance.postgres.port
    dbname       = var.db_name
    username     = var.db_username
    password     = random_password.db_master.result
    sslmode      = "require"
    iam_user     = var.db_iam_username
    dbeaver_note = "Run bash infra/aws/db-tunnel.sh then connect DBeaver to localhost:15432"
  })
}
