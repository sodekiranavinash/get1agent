module "api_gateway" {
  count  = var.enable_api_gateway ? 1 : 0
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

  lambda_routes = var.enable_backend_lambdas && var.enable_rds ? {
    health_db = {
      method               = "GET"
      path                 = "/health/db"
      lambda_invoke_arn    = module.health_check[0].invoke_arn
      lambda_function_name = module.health_check[0].function_name
      authorization_type   = "NONE"
    }
    user_settings_get = {
      method               = "GET"
      path                 = "/v1/user/settings"
      lambda_invoke_arn    = module.account_settings[0].invoke_arn
      lambda_function_name = module.account_settings[0].function_name
      authorization_type   = "JWT"
    }
    user_settings_update = {
      method               = "POST"
      path                 = "/v1/user/settings"
      lambda_invoke_arn    = module.account_settings[0].invoke_arn
      lambda_function_name = module.account_settings[0].function_name
      authorization_type   = "JWT"
    }
    knowledge_bases_list = {
      method               = "GET"
      path                 = "/v1/knowledge-bases"
      lambda_invoke_arn    = module.knowledge_bases[0].invoke_arn
      lambda_function_name = module.knowledge_bases[0].function_name
      authorization_type   = "JWT"
    }
    knowledge_bases_create = {
      method               = "POST"
      path                 = "/v1/knowledge-bases"
      lambda_invoke_arn    = module.knowledge_bases[0].invoke_arn
      lambda_function_name = module.knowledge_bases[0].function_name
      authorization_type   = "JWT"
    }
    knowledge_bases_get = {
      method               = "GET"
      path                 = "/v1/knowledge-bases/{id}"
      lambda_invoke_arn    = module.knowledge_bases[0].invoke_arn
      lambda_function_name = module.knowledge_bases[0].function_name
      authorization_type   = "JWT"
    }
    knowledge_bases_delete = {
      method               = "DELETE"
      path                 = "/v1/knowledge-bases/{id}"
      lambda_invoke_arn    = module.knowledge_bases[0].invoke_arn
      lambda_function_name = module.knowledge_bases[0].function_name
      authorization_type   = "JWT"
    }
    knowledge_bases_presign = {
      method               = "POST"
      path                 = "/v1/knowledge-bases/{id}/documents/presign"
      lambda_invoke_arn    = module.knowledge_bases[0].invoke_arn
      lambda_function_name = module.knowledge_bases[0].function_name
      authorization_type   = "JWT"
    }
    knowledge_bases_inline = {
      method               = "POST"
      path                 = "/v1/knowledge-bases/{id}/documents/inline"
      lambda_invoke_arn    = module.knowledge_bases[0].invoke_arn
      lambda_function_name = module.knowledge_bases[0].function_name
      authorization_type   = "JWT"
    }
    knowledge_bases_complete = {
      method               = "POST"
      path                 = "/v1/knowledge-bases/{id}/documents/{docId}/complete"
      lambda_invoke_arn    = module.knowledge_bases[0].invoke_arn
      lambda_function_name = module.knowledge_bases[0].function_name
      authorization_type   = "JWT"
    }
    knowledge_bases_local_upload = {
      method               = "POST"
      path                 = "/v1/knowledge-bases/{id}/documents/{docId}/upload"
      lambda_invoke_arn    = module.knowledge_bases[0].invoke_arn
      lambda_function_name = module.knowledge_bases[0].function_name
      authorization_type   = "JWT"
    }
    knowledge_bases_document_delete = {
      method               = "DELETE"
      path                 = "/v1/knowledge-bases/{id}/documents/{docId}"
      lambda_invoke_arn    = module.knowledge_bases[0].invoke_arn
      lambda_function_name = module.knowledge_bases[0].function_name
      authorization_type   = "JWT"
    }
  } : {}
}
