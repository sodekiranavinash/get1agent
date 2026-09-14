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

  # /health is a MOCK 200 integration inside the api_gateway module (no Lambda).
  lambda_routes = var.enable_backend_lambdas ? {
    user_settings_get = {
      method               = "GET"
      path                 = "/v1/user/settings"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    user_settings_update = {
      method               = "POST"
      path                 = "/v1/user/settings"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    knowledge_bases_list = {
      method               = "GET"
      path                 = "/v1/knowledge-bases"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    knowledge_bases_create = {
      method               = "POST"
      path                 = "/v1/knowledge-bases"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    knowledge_bases_tags = {
      method               = "GET"
      path                 = "/v1/knowledge-bases/tags"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    knowledge_bases_events = {
      method               = "GET"
      path                 = "/v1/knowledge-bases/events"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    knowledge_bases_get = {
      method               = "GET"
      path                 = "/v1/knowledge-bases/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    knowledge_bases_delete = {
      method               = "DELETE"
      path                 = "/v1/knowledge-bases/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    knowledge_bases_presign = {
      method               = "POST"
      path                 = "/v1/knowledge-bases/{id}/documents/presign"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    knowledge_bases_inline = {
      method               = "POST"
      path                 = "/v1/knowledge-bases/{id}/documents/inline"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    knowledge_bases_complete = {
      method               = "POST"
      path                 = "/v1/knowledge-bases/{id}/documents/{docId}/complete"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    knowledge_bases_document_delete = {
      method               = "DELETE"
      path                 = "/v1/knowledge-bases/{id}/documents/{docId}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    agent_skills_list = {
      method               = "GET"
      path                 = "/v1/agent-skills"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    agent_skills_create = {
      method               = "POST"
      path                 = "/v1/agent-skills"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    agent_skills_tools = {
      method               = "GET"
      path                 = "/v1/agent-skills/tools"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    agent_skills_parse = {
      method               = "POST"
      path                 = "/v1/agent-skills/parse"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    agent_skills_get = {
      method               = "GET"
      path                 = "/v1/agent-skills/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    agent_skills_update = {
      method               = "PUT"
      path                 = "/v1/agent-skills/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    agent_skills_delete = {
      method               = "DELETE"
      path                 = "/v1/agent-skills/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    knowledge_mcp = {
      method               = "POST"
      path                 = "/mcp"
      lambda_invoke_arn    = module.knowledge_mcp[0].invoke_arn
      lambda_function_name = module.knowledge_mcp[0].function_name
      authorization_type   = "JWT"
    }
    web_search_mcp = {
      method               = "POST"
      path                 = "/mcp/web-search"
      lambda_invoke_arn    = module.web_search[0].invoke_arn
      lambda_function_name = module.web_search[0].function_name
      authorization_type   = "JWT"
    }
    code_interpreter_mcp = {
      method               = "POST"
      path                 = "/mcp/code-interpreter"
      lambda_invoke_arn    = module.code_interpreter[0].invoke_arn
      lambda_function_name = module.code_interpreter[0].function_name
      authorization_type   = "JWT"
    }
    admin_mcp_tools = {
      method               = "GET"
      path                 = "/v1/admin/mcp/tools"
      lambda_invoke_arn    = module.mcp_tester[0].invoke_arn
      lambda_function_name = module.mcp_tester[0].function_name
      authorization_type   = "JWT"
    }
    admin_mcp_call = {
      method               = "POST"
      path                 = "/v1/admin/mcp/call"
      lambda_invoke_arn    = module.mcp_tester[0].invoke_arn
      lambda_function_name = module.mcp_tester[0].function_name
      authorization_type   = "JWT"
    }
  } : {}
}
