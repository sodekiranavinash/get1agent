output "app_public_ip" {
  description = "App EC2 Elastic IP"
  value       = try(module.data_plane[0].app_public_ip, null)
}

output "app_instance_id" {
  description = "App EC2 instance ID"
  value       = try(module.data_plane[0].app_instance_id, null)
}

output "api_base_url" {
  description = "API URL via nginx on port 80"
  value       = try(module.data_plane[0].api_base_url, null)
}

output "api_public_hostname" {
  description = "Cloudflare DNS hostname for the API (A record -> app_public_ip)"
  value       = try(module.data_plane[0].api_public_hostname, null)
}

output "ecr_repository_url" {
  description = "ECR repository for backend Docker images"
  value       = try(module.data_plane[0].ecr_repository_url, null)
}

output "postgres_endpoint" {
  description = "RDS hostname (private)"
  value       = try(module.data_plane[0].postgres_endpoint, null)
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
