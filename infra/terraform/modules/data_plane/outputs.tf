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
  description = "EC2 jumpbox instance ID (SSM DB tunnel)"
  value       = aws_instance.jumpbox.id
}

output "postgres_endpoint" {
  description = "RDS hostname (private; reach via SSM tunnel)"
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

output "postgres_credentials_secret_arn" {
  value = aws_secretsmanager_secret.db_credentials.arn
}

output "postgres_connection_secret_arn" {
  value = aws_secretsmanager_secret.db_connection.arn
}

output "db_tunnel_command" {
  value = "bash infra/aws/db-tunnel.sh"
}

output "ssm_tunnel_command" {
  value = "aws ssm start-session --target ${aws_instance.jumpbox.id} --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters '{\"host\":[\"${aws_db_instance.postgres.address}\"],\"portNumber\":[\"5432\"],\"localPortNumber\":[\"5432\"]}'"
}

# Backward-compatible alias for scripts still using app_instance_id.
output "app_instance_id" {
  value = aws_instance.jumpbox.id
}
