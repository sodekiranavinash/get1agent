module "api_gateway" {
  source = "../../modules/api_gateway"

  name_prefix          = "get1agent-prod"
  api_hostname         = var.api_hostname
  auth0_domain         = var.auth0_domain
  auth0_audience       = var.auth0_audience
  enable_custom_domain = var.enable_api_custom_domain

  cors_allow_origins = [
    "https://www.get1agent.com",
    "http://localhost:5173",
  ]

  lambda_routes = var.enable_vpc_rds ? {
    health_db = {
      method               = "GET"
      path                 = "/health/db"
      lambda_invoke_arn    = module.health_check[0].invoke_arn
      lambda_function_name = module.health_check[0].function_name
      authorization_type   = "NONE"
    }
  } : {}
}
