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

output "knowledge_bases_bucket_name" {
  description = "S3 bucket holding knowledge base documents + retrieval artifacts"
  value       = try(module.knowledge_storage[0].bucket_name, null)
}

output "dynamodb_table_name" {
  description = "Single DynamoDB table holding all operational data"
  value       = try(module.database[0].table_name, null)
}

output "vector_bucket_name" {
  description = "S3 Vectors bucket holding the per-user embedding indexes"
  value       = try(module.vectors[0].vector_bucket_name, null)
}

output "ingestion_queue_url" {
  description = "SQS queue feeding the ingestion pipeline"
  value       = try(module.ingestion[0].queue_url, null)
}

output "ingestion_state_machine_arn" {
  description = "Step Functions Standard state machine for ingestion"
  value       = try(module.ingestion[0].state_machine_arn, null)
}
