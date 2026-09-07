output "vpc_id" {
  description = "VPC ID for the data plane"
  value       = aws_vpc.main.id
}

output "app_public_ip" {
  description = "Elastic IP of the app EC2 instance"
  value       = aws_eip.app.public_ip
}

output "app_instance_id" {
  description = "EC2 instance ID (SSM deploy + port forwarding)"
  value       = aws_instance.app.id
}

output "app_ssh_key_secret_arn" {
  description = "Secrets Manager ARN containing the app EC2 private SSH key"
  value       = aws_secretsmanager_secret.app_ssh_key.arn
}

output "api_base_url" {
  description = "FastAPI base URL after deploy-backend workflow runs"
  value       = "http://${aws_eip.app.public_ip}:${var.api_port}"
}

output "ecr_repository_url" {
  description = "ECR repository URL for the FastAPI image"
  value       = aws_ecr_repository.api.repository_url
}

output "postgres_endpoint" {
  description = "RDS hostname (private; reach via app EC2 SSH tunnel)"
  value       = aws_db_instance.postgres.address
}

output "postgres_port" {
  description = "RDS port"
  value       = aws_db_instance.postgres.port
}

output "postgres_db_name" {
  description = "Initial database name"
  value       = var.db_name
}

output "postgres_username" {
  description = "Master database username"
  value       = var.db_username
}

output "postgres_credentials_secret_arn" {
  description = "Secrets Manager ARN with DB username/password"
  value       = aws_secretsmanager_secret.db_credentials.arn
}

output "postgres_connection_secret_arn" {
  description = "Secrets Manager ARN with full connection strings"
  value       = aws_secretsmanager_secret.db_connection.arn
}

output "ssh_tunnel_command" {
  description = "SSH local port forward for psql or DBeaver local mode"
  value       = "ssh -i ~/.ssh/${var.name_prefix}-app.pem -L 5432:${aws_db_instance.postgres.address}:5432 ec2-user@${aws_eip.app.public_ip} -N"
}

output "ssm_tunnel_command" {
  description = "SSM port forward without SSH key file"
  value       = "aws ssm start-session --target ${aws_instance.app.id} --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters '{\"host\":[\"${aws_db_instance.postgres.address}\"],\"portNumber\":[\"5432\"],\"localPortNumber\":[\"5432\"]}'"
}

output "dbeaver_ssh_host" {
  description = "DBeaver SSH tunnel host"
  value       = aws_eip.app.public_ip
}

output "dbeaver_postgres_host" {
  description = "DBeaver main tab host (via SSH tunnel through app EC2)"
  value       = aws_db_instance.postgres.address
}
