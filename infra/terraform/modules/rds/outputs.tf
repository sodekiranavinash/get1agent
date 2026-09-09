output "postgres_endpoint" {
  description = "RDS hostname (private VPC only)"
  value       = aws_db_instance.postgres.address
}

output "postgres_port" {
  value = aws_db_instance.postgres.port
}

output "postgres_db_name" {
  value = var.db_name
}

output "postgres_username" {
  value = var.db_username
}

output "db_iam_username" {
  value = var.db_iam_username
}

output "postgres_resource_id" {
  description = "RDS resource ID for rds-db:connect IAM policy"
  value       = aws_db_instance.postgres.resource_id
}

output "postgres_credentials_parameter_name" {
  value = aws_ssm_parameter.db_credentials.name
}

output "postgres_connection_parameter_name" {
  value = aws_ssm_parameter.db_connection.name
}
