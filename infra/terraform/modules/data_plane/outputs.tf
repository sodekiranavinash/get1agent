output "vpc_id" {
  description = "VPC ID for the data plane"
  value       = aws_vpc.main.id
}

output "app_public_ip" {
  description = "Elastic IP of the Kong EC2 instance"
  value       = aws_eip.app.public_ip
}

output "app_instance_id" {
  description = "EC2 instance ID (SSM deploy + DB tunnel)"
  value       = aws_instance.app.id
}

output "api_base_url" {
  description = "Kong proxy URL on port 80 (point api.<domain> A record here in Cloudflare)"
  value       = "http://${aws_eip.app.public_ip}"
}

output "api_public_hostname" {
  description = "Cloudflare DNS: proxied A record api -> app_public_ip"
  value       = var.api_hostname
}

output "kong_ui_hostname" {
  description = "Cloudflare DNS: proxied A record kong -> app_public_ip"
  value       = var.kong_ui_hostname
}

output "kong_admin_credentials_secret_arn" {
  description = "Secrets Manager ARN with Kong Manager UI admin username/password"
  value       = aws_secretsmanager_secret.kong_admin_credentials.arn
}

output "postgres_endpoint" {
  description = "RDS hostname (private; reach via SSM tunnel)"
  value       = aws_db_instance.postgres.address
}

output "postgres_port" {
  description = "RDS port"
  value       = aws_db_instance.postgres.port
}

output "postgres_db_name" {
  description = "App database name"
  value       = var.db_name
}

output "kong_db_name" {
  description = "Kong configuration database name"
  value       = var.kong_db_name
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

output "db_tunnel_command" {
  description = "Start local SSM port forward to RDS for DBeaver"
  value       = "bash infra/aws/db-tunnel.sh"
}

output "ssm_tunnel_command" {
  description = "Raw AWS CLI SSM port forward to RDS"
  value       = "aws ssm start-session --target ${aws_instance.app.id} --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters '{\"host\":[\"${aws_db_instance.postgres.address}\"],\"portNumber\":[\"5432\"],\"localPortNumber\":[\"5432\"]}'"
}
