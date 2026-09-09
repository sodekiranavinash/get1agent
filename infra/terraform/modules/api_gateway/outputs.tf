output "api_id" {
  value = aws_apigatewayv2_api.this.id
}

output "api_endpoint" {
  description = "Default execute-api URL (works before custom domain is live)"
  value       = aws_apigatewayv2_stage.this.invoke_url
}

output "api_custom_domain" {
  description = "Custom domain URL (after enable_custom_domain + DNS)"
  value       = var.enable_custom_domain ? "https://${var.api_hostname}" : null
}

output "api_hostname" {
  value = var.api_hostname
}

output "api_gateway_domain_target" {
  description = "Cloudflare CNAME target for api.<domain> (DNS only / grey cloud recommended)"
  value       = var.enable_custom_domain ? aws_apigatewayv2_domain_name.api[0].domain_name_configuration[0].target_domain_name : null
}

output "acm_validation_records" {
  description = "Add these CNAME records in Cloudflare to validate the ACM certificate"
  value = var.enable_custom_domain ? {
    for dvo in aws_acm_certificate.api[0].domain_validation_options : dvo.domain_name => {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  } : {}
}

output "auth0_audience" {
  value = var.auth0_audience
}

output "jwt_authorizer_id" {
  value = aws_apigatewayv2_authorizer.auth0.id
}
