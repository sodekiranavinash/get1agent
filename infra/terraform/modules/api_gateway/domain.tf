resource "aws_acm_certificate" "api" {
  count = var.enable_custom_domain ? 1 : 0

  domain_name       = var.api_hostname
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = var.tags
}

resource "aws_acm_certificate_validation" "api" {
  count = var.enable_custom_domain ? 1 : 0

  certificate_arn = aws_acm_certificate.api[0].arn

  # Add ACM validation CNAME in Cloudflare (output acm_validation_records), then re-apply.
  timeouts {
    create = "45m"
  }
}

resource "aws_apigatewayv2_domain_name" "api" {
  count = var.enable_custom_domain ? 1 : 0

  domain_name = var.api_hostname

  domain_name_configuration {
    certificate_arn = aws_acm_certificate.api[0].arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }

  tags = var.tags

  depends_on = [aws_acm_certificate_validation.api]
}

resource "aws_apigatewayv2_api_mapping" "api" {
  count = var.enable_custom_domain ? 1 : 0

  api_id      = aws_apigatewayv2_api.this.id
  domain_name = aws_apigatewayv2_domain_name.api[0].id
  stage       = aws_apigatewayv2_stage.this.id
}
