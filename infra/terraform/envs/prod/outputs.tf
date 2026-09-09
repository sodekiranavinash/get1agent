output "api_url" {
  description = "Public API URL (custom domain when enabled, else execute-api URL)"
  value       = coalesce(module.api_gateway.api_custom_domain, module.api_gateway.api_endpoint)
}

output "api_gateway_endpoint" {
  description = "Default execute-api URL (before custom domain is live)"
  value       = module.api_gateway.api_endpoint
}

output "api_hostname" {
  description = "API custom domain hostname"
  value       = module.api_gateway.api_hostname
}

output "api_gateway_cname_target" {
  description = "Cloudflare CNAME target for api.get1agent.com"
  value       = module.api_gateway.api_gateway_domain_target
}

output "acm_validation_records" {
  description = "ACM DNS validation records to add in Cloudflare"
  value       = module.api_gateway.acm_validation_records
}

output "auth0_audience" {
  description = "Auth0 API audience (must match frontend + Auth0 API identifier)"
  value       = module.api_gateway.auth0_audience
}

output "jumpbox_instance_id" {
  description = "On-demand jumpbox EC2 (stop when idle to avoid public IPv4 charges)"
  value       = try(module.vpc_rds[0].jumpbox_instance_id, null)
}

output "db_access_command" {
  description = "Start jumpbox, tunnel to RDS, stop on exit (minimal IPv4 cost)"
  value       = try(module.vpc_rds[0].db_access_command, null)
}

output "app_instance_id" {
  description = "Alias for jumpbox_instance_id"
  value       = try(module.vpc_rds[0].app_instance_id, null)
}

output "postgres_endpoint" {
  description = "RDS hostname (private)"
  value       = try(module.vpc_rds[0].postgres_endpoint, null)
}

output "postgres_db_name" {
  value = try(module.vpc_rds[0].postgres_db_name, null)
}

output "postgres_username" {
  value = try(module.vpc_rds[0].postgres_username, null)
}

output "db_iam_username" {
  value = try(module.vpc_rds[0].db_iam_username, null)
}

output "postgres_credentials_parameter_name" {
  description = "SSM path for master DB credentials (SecureString)"
  value       = try(module.vpc_rds[0].postgres_credentials_parameter_name, null)
}

output "postgres_connection_parameter_name" {
  description = "SSM path for connection JSON (SecureString)"
  value       = try(module.vpc_rds[0].postgres_connection_parameter_name, null)
}
