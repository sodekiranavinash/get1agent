output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "private_subnet_ids" {
  description = "Private subnet IDs for VPC Lambdas"
  value       = [aws_subnet.private_a.id, aws_subnet.private_b.id]
}

output "postgres_security_group_id" {
  description = "RDS security group ID"
  value       = aws_security_group.postgres.id
}

output "postgres_resource_id" {
  description = "RDS resource ID for rds-db:connect IAM policy"
  value       = aws_db_instance.postgres.resource_id
}

output "jumpbox_instance_id" {
  description = "On-demand jumpbox EC2 (stop when idle to avoid public IPv4 charges)"
  value       = aws_instance.jumpbox.id
}

output "db_access_command" {
  description = "Start jumpbox, SSM tunnel to RDS, stop on exit"
  value       = "bash infra/aws/db-access.sh"
}

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

output "db_iam_username" {
  value = var.db_iam_username
}

output "postgres_username" {
  value = var.db_username
}

output "postgres_credentials_parameter_name" {
  description = "SSM Parameter Store path for master DB username/password"
  value       = aws_ssm_parameter.db_credentials.name
}

output "postgres_connection_parameter_name" {
  description = "SSM Parameter Store path for full connection JSON"
  value       = aws_ssm_parameter.db_connection.name
}

# Backward-compatible alias for scripts still using app_instance_id.
output "app_instance_id" {
  value = aws_instance.jumpbox.id
}
