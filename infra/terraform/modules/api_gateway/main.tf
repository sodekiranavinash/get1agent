resource "aws_apigatewayv2_api" "this" {
  name          = "${var.name_prefix}-http-api"
  protocol_type = "HTTP"
  description   = "get1agent HTTP API (Auth0 JWT, Lambda integrations)"

  cors_configuration {
    allow_credentials = false
    allow_headers     = ["authorization", "content-type", "x-request-id"]
    allow_methods     = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    allow_origins     = var.cors_allow_origins
    expose_headers    = ["x-request-id"]
    max_age           = 300
  }

  tags = var.tags
}

resource "aws_apigatewayv2_authorizer" "auth0" {
  api_id           = aws_apigatewayv2_api.this.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "auth0"

  jwt_configuration {
    audience = [var.auth0_audience]
    issuer   = "https://${var.auth0_domain}/"
  }
}

resource "aws_apigatewayv2_stage" "this" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = var.stage_name
  auto_deploy = true

  default_route_settings {
    throttling_burst_limit = var.stage_throttle_burst_limit
    throttling_rate_limit  = var.stage_throttle_rate_limit
  }

  dynamic "route_settings" {
    for_each = {
      for k, v in var.lambda_routes : k => v
      if v.throttle_burst_limit != null || v.throttle_rate_limit != null
    }

    content {
      route_key              = "${route_settings.value.method} ${route_settings.value.path}"
      throttling_burst_limit = coalesce(route_settings.value.throttle_burst_limit, var.stage_throttle_burst_limit)
      throttling_rate_limit  = coalesce(route_settings.value.throttle_rate_limit, var.stage_throttle_rate_limit)
    }
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      protocol       = "$context.protocol"
      responseLength = "$context.responseLength"
      errorMessage   = "$context.error.message"
    })
  }

  tags = var.tags

  depends_on = [aws_cloudwatch_log_group.api]
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/apigateway/${var.name_prefix}-http-api"
  retention_in_days = 7
  tags              = var.tags
}

# Minimal health route (no auth) — no Lambda required.
resource "aws_apigatewayv2_integration" "health" {
  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.health.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "health" {
  api_id             = aws_apigatewayv2_api.this.id
  route_key          = "GET /health"
  target             = "integrations/${aws_apigatewayv2_integration.health.id}"
  authorization_type = "NONE"
}

resource "aws_lambda_function" "health" {
  function_name = "${var.name_prefix}-api-health"
  role          = aws_iam_role.health_lambda.arn
  runtime       = "python3.12"
  handler       = "index.handler"
  timeout       = 3
  memory_size   = 128
  architectures = ["arm64"]

  filename         = data.archive_file.health.output_path
  source_code_hash = data.archive_file.health.output_base64sha256

  tags = var.tags
}

data "archive_file" "health" {
  type        = "zip"
  output_path = "${path.module}/.build/health-lambda.zip"

  source {
    content  = <<-PY
import json

def handler(event, context):
    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"status": "ok", "service": "get1agent-api"}),
    }
PY
    filename = "index.py"
  }
}

resource "aws_iam_role" "health_lambda" {
  name = "${var.name_prefix}-api-health-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "health_lambda_logs" {
  role       = aws_iam_role.health_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_permission" "health_apigw" {
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.health.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*/*"
}

# Optional Lambda routes (add entries as you build serverless APIs).
resource "aws_apigatewayv2_integration" "lambda" {
  for_each = var.lambda_routes

  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_uri        = each.value.lambda_invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "lambda" {
  for_each = var.lambda_routes

  api_id    = aws_apigatewayv2_api.this.id
  route_key = "${each.value.method} ${each.value.path}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda[each.key].id}"

  authorization_type = each.value.authorization_type
  authorizer_id      = each.value.authorization_type == "JWT" ? aws_apigatewayv2_authorizer.auth0.id : null
}

resource "aws_lambda_permission" "lambda_apigw" {
  for_each = var.lambda_routes

  action        = "lambda:InvokeFunction"
  function_name = each.value.lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*/*"
}
