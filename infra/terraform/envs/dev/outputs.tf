output "bastion_public_ip" {
  description = "Deprecated alias — use app_public_ip"
  value       = try(module.data_plane[0].app_public_ip, null)
}

output "bastion_instance_id" {
  description = "Deprecated alias — use app_instance_id"
  value       = try(module.data_plane[0].app_instance_id, null)
}

output "bastion_ssh_key_secret_arn" {
  description = "Deprecated alias — use app_ssh_key_secret_arn"
  value       = try(module.data_plane[0].app_ssh_key_secret_arn, null)
}

output "app_public_ip" {
  description = "App EC2 Elastic IP"
  value       = try(module.data_plane[0].app_public_ip, null)
}

output "app_instance_id" {
  description = "App EC2 instance ID"
  value       = try(module.data_plane[0].app_instance_id, null)
}

output "app_ssh_key_secret_arn" {
  description = "Secrets Manager ARN with SSH private key for DBeaver"
  value       = try(module.data_plane[0].app_ssh_key_secret_arn, null)
}

output "api_base_url" {
  description = "FastAPI URL after backend deploy"
  value       = try(module.data_plane[0].api_base_url, null)
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

output "ssh_tunnel_command" {
  value = try(module.data_plane[0].ssh_tunnel_command, null)
}

output "ssm_tunnel_command" {
  value = try(module.data_plane[0].ssm_tunnel_command, null)
}

output "dbeaver_ssh_host" {
  value = try(module.data_plane[0].dbeaver_ssh_host, null)
}

output "dbeaver_postgres_host" {
  value = try(module.data_plane[0].dbeaver_postgres_host, null)
}
