output "app_public_ip" {
  description = "Kong EC2 Elastic IP"
  value       = try(module.data_plane[0].app_public_ip, null)
}

output "app_instance_id" {
  description = "Kong EC2 instance ID"
  value       = try(module.data_plane[0].app_instance_id, null)
}

output "api_base_url" {
  description = "Kong proxy URL on port 80"
  value       = try(module.data_plane[0].api_base_url, null)
}

output "api_public_hostname" {
  description = "Cloudflare DNS hostname for the API (A record -> app_public_ip)"
  value       = try(module.data_plane[0].api_public_hostname, null)
}

output "kong_ui_hostname" {
  description = "Cloudflare DNS hostname for Kong Manager UI (A record -> app_public_ip)"
  value       = try(module.data_plane[0].kong_ui_hostname, null)
}

output "kong_admin_credentials_secret_arn" {
  description = "Secrets Manager ARN with Kong Manager UI credentials"
  value       = try(module.data_plane[0].kong_admin_credentials_secret_arn, null)
}

output "postgres_endpoint" {
  description = "RDS hostname (private)"
  value       = try(module.data_plane[0].postgres_endpoint, null)
}

output "postgres_db_name" {
  description = "App database name"
  value       = try(module.data_plane[0].postgres_db_name, null)
}

output "postgres_username" {
  description = "Master database username"
  value       = try(module.data_plane[0].postgres_username, null)
}

output "kong_db_name" {
  description = "Kong configuration database name"
  value       = try(module.data_plane[0].kong_db_name, null)
}

output "kong_db_iam_username" {
  description = "PostgreSQL IAM user for Kong"
  value       = try(module.data_plane[0].kong_db_iam_username, null)
}

output "db_iam_username" {
  description = "PostgreSQL IAM user for future serverless services"
  value       = try(module.data_plane[0].db_iam_username, null)
}

output "kong_image" {
  description = "Kong Gateway Docker image"
  value       = try(module.data_plane[0].kong_image, null)
}

output "postgres_credentials_secret_arn" {
  description = "Secrets Manager ARN with master DB username/password"
  value       = try(module.data_plane[0].postgres_credentials_secret_arn, null)
}

output "postgres_connection_secret_arn" {
  description = "Secrets Manager ARN with DB credentials"
  value       = try(module.data_plane[0].postgres_connection_secret_arn, null)
}

output "db_tunnel_command" {
  description = "SSM tunnel to RDS for DBeaver"
  value       = try(module.data_plane[0].db_tunnel_command, null)
}

output "ssm_tunnel_command" {
  value = try(module.data_plane[0].ssm_tunnel_command, null)
}
