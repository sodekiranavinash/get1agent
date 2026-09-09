output "api_url" {
  description = "Public API URL (custom domain when enabled, else execute-api URL)"
  value = try(
    "${trimsuffix(coalesce(module.api_gateway[0].api_custom_domain, module.api_gateway[0].api_endpoint), "/")}/",
    null,
  )
}

output "api_gateway_endpoint" {
  description = "Default execute-api URL (before custom domain is live)"
  value       = try(module.api_gateway[0].api_endpoint, null)
}

output "api_hostname" {
  description = "API custom domain hostname"
  value       = try(module.api_gateway[0].api_hostname, null)
}

output "api_gateway_cname_target" {
  description = "Cloudflare CNAME target for api.get1agent.com"
  value       = try(module.api_gateway[0].api_gateway_domain_target, null)
}

output "acm_validation_records" {
  description = "ACM DNS validation records to add in Cloudflare"
  value       = try(module.api_gateway[0].acm_validation_records, null)
}

output "auth0_audience" {
  description = "Auth0 API audience (must match frontend + Auth0 API identifier)"
  value       = try(module.api_gateway[0].auth0_audience, null)
}

output "jumpbox_instance_id" {
  description = "On-demand jumpbox EC2 (stop when idle to avoid public IPv4 charges)"
  value       = try(module.network[0].jumpbox_instance_id, null)
}

output "db_access_command" {
  description = "Start jumpbox, tunnel to RDS, stop on exit (minimal IPv4 cost)"
  value       = try(module.network[0].db_access_command, null)
}

output "postgres_endpoint" {
  description = "RDS hostname (private)"
  value       = try(module.rds[0].postgres_endpoint, null)
}

output "postgres_db_name" {
  value = try(module.rds[0].postgres_db_name, null)
}

output "postgres_username" {
  value = try(module.rds[0].postgres_username, null)
}

output "db_iam_username" {
  value = try(module.rds[0].db_iam_username, null)
}

output "postgres_credentials_parameter_name" {
  description = "SSM path for master DB credentials (SecureString)"
  value       = try(module.rds[0].postgres_credentials_parameter_name, null)
}

output "postgres_connection_parameter_name" {
  description = "SSM path for connection JSON (SecureString)"
  value       = try(module.rds[0].postgres_connection_parameter_name, null)
}
