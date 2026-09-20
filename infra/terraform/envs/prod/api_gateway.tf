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
  lambda_routes = var.enable_backend_lambdas ? merge({
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
    agent_skills_mcp_servers = {
      method               = "GET"
      path                 = "/v1/agent-skills/mcp-servers"
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
    agent_skills_catalog = {
      method               = "GET"
      path                 = "/v1/agent-skills/catalog"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    agent_skills_registry = {
      method               = "GET"
      path                 = "/v1/agent-skills/registry"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    agent_skills_import_preview = {
      method               = "POST"
      path                 = "/v1/agent-skills/import/preview"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    agent_skills_import = {
      method               = "POST"
      path                 = "/v1/agent-skills/import"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    agent_skills_resolve_repo = {
      method               = "POST"
      path                 = "/v1/agent-skills/resolve-repo"
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
    agents_list = {
      method               = "GET"
      path                 = "/v1/agents"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    agents_create = {
      method               = "POST"
      path                 = "/v1/agents"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    agents_library = {
      method               = "GET"
      path                 = "/v1/agents/library"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    agents_library_install = {
      method               = "POST"
      path                 = "/v1/agents/library/{id}/install"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    agents_get = {
      method               = "GET"
      path                 = "/v1/agents/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    agents_update = {
      method               = "PUT"
      path                 = "/v1/agents/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    agents_delete = {
      method               = "DELETE"
      path                 = "/v1/agents/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    agents_verify = {
      method               = "POST"
      path                 = "/v1/agents/{id}/verify"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    agents_publish = {
      method               = "POST"
      path                 = "/v1/agents/{id}/publish"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    agents_unpublish = {
      method               = "POST"
      path                 = "/v1/agents/{id}/unpublish"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    storage_files_list = {
      method               = "GET"
      path                 = "/v1/storage/files"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    storage_presign = {
      method               = "POST"
      path                 = "/v1/storage/presign"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    storage_complete = {
      method               = "POST"
      path                 = "/v1/storage/files/{fileId}/complete"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    storage_delete = {
      method               = "DELETE"
      path                 = "/v1/storage/files/{fileId}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    agents_runs = {
      method               = "GET"
      path                 = "/v1/agents/{id}/runs"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    conversations_list = {
      method               = "GET"
      path                 = "/v1/conversations"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    conversations_create = {
      method               = "POST"
      path                 = "/v1/conversations"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    conversations_get = {
      method               = "GET"
      path                 = "/v1/conversations/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    conversations_update = {
      method               = "PATCH"
      path                 = "/v1/conversations/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    conversations_delete = {
      method               = "DELETE"
      path                 = "/v1/conversations/{id}"
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
    mcp_catalog = {
      method               = "GET"
      path                 = "/v1/mcp/catalog"
      lambda_invoke_arn    = module.mcp_connections[0].invoke_arn
      lambda_function_name = module.mcp_connections[0].function_name
      authorization_type   = "JWT"
    }
    mcp_registry = {
      method               = "GET"
      path                 = "/v1/mcp/registry"
      lambda_invoke_arn    = module.mcp_connections[0].invoke_arn
      lambda_function_name = module.mcp_connections[0].function_name
      authorization_type   = "JWT"
    }
    mcp_connections_list = {
      method               = "GET"
      path                 = "/v1/mcp/connections"
      lambda_invoke_arn    = module.mcp_connections[0].invoke_arn
      lambda_function_name = module.mcp_connections[0].function_name
      authorization_type   = "JWT"
    }
    mcp_connections_create = {
      method               = "POST"
      path                 = "/v1/mcp/connections"
      lambda_invoke_arn    = module.mcp_connections[0].invoke_arn
      lambda_function_name = module.mcp_connections[0].function_name
      authorization_type   = "JWT"
    }
    mcp_connections_get = {
      method               = "GET"
      path                 = "/v1/mcp/connections/{id}"
      lambda_invoke_arn    = module.mcp_connections[0].invoke_arn
      lambda_function_name = module.mcp_connections[0].function_name
      authorization_type   = "JWT"
    }
    mcp_connections_delete = {
      method               = "DELETE"
      path                 = "/v1/mcp/connections/{id}"
      lambda_invoke_arn    = module.mcp_connections[0].invoke_arn
      lambda_function_name = module.mcp_connections[0].function_name
      authorization_type   = "JWT"
    }
    mcp_connections_update = {
      method               = "PATCH"
      path                 = "/v1/mcp/connections/{id}"
      lambda_invoke_arn    = module.mcp_connections[0].invoke_arn
      lambda_function_name = module.mcp_connections[0].function_name
      authorization_type   = "JWT"
    }
    mcp_connections_refresh = {
      method               = "POST"
      path                 = "/v1/mcp/connections/{id}/refresh"
      lambda_invoke_arn    = module.mcp_connections[0].invoke_arn
      lambda_function_name = module.mcp_connections[0].function_name
      authorization_type   = "JWT"
    }
    mcp_connections_authorize = {
      method               = "POST"
      path                 = "/v1/mcp/connections/{id}/authorize"
      lambda_invoke_arn    = module.mcp_connections[0].invoke_arn
      lambda_function_name = module.mcp_connections[0].function_name
      authorization_type   = "JWT"
    }
    mcp_connections_token = {
      method               = "POST"
      path                 = "/v1/mcp/connections/{id}/token"
      lambda_invoke_arn    = module.mcp_connections[0].invoke_arn
      lambda_function_name = module.mcp_connections[0].function_name
      authorization_type   = "JWT"
    }
    mcp_connections_tools = {
      method               = "GET"
      path                 = "/v1/mcp/connections/{id}/tools"
      lambda_invoke_arn    = module.mcp_connections[0].invoke_arn
      lambda_function_name = module.mcp_connections[0].function_name
      authorization_type   = "JWT"
    }
    mcp_connections_tool_update = {
      method               = "PATCH"
      path                 = "/v1/mcp/connections/{id}/tools"
      lambda_invoke_arn    = module.mcp_connections[0].invoke_arn
      lambda_function_name = module.mcp_connections[0].function_name
      authorization_type   = "JWT"
    }
    mcp_connections_call = {
      method               = "POST"
      path                 = "/v1/mcp/connections/{id}/call"
      lambda_invoke_arn    = module.mcp_connections[0].invoke_arn
      lambda_function_name = module.mcp_connections[0].function_name
      authorization_type   = "JWT"
    }
    mcp_oauth_callback = {
      method               = "GET"
      path                 = "/v1/mcp/oauth/callback"
      lambda_invoke_arn    = module.mcp_connections[0].invoke_arn
      lambda_function_name = module.mcp_connections[0].function_name
      authorization_type   = "NONE"
    }
    remote_mcp = {
      method               = "POST"
      path                 = "/mcp/remote"
      lambda_invoke_arn    = module.mcp_connections[0].invoke_arn
      lambda_function_name = module.mcp_connections[0].function_name
      authorization_type   = "JWT"
    }
  }, var.enable_agent_runtime ? {
    # Auth is enforced at the gateway (JWT authorizer); the Lambda only launches
    # a Lambda MicroVM and returns its endpoint + ingress token.
    agent_run_session = {
      method               = "POST"
      path                 = "/v1/agent-run/session"
      lambda_invoke_arn    = module.agent_runtime[0].control_plane_invoke_arn
      lambda_function_name = module.agent_runtime[0].control_plane_function_name
      authorization_type   = "JWT"
    }
  } : {}) : {}
}
