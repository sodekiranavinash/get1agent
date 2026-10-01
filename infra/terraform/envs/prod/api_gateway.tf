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

  # Common throttle for every route (per-route limits for the heavy MCP/agent
  # routes are set on the routes below).
  stage_throttle_burst_limit = var.stage_throttle_burst_limit
  stage_throttle_rate_limit  = var.stage_throttle_rate_limit

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
    workflows_list = {
      method               = "GET"
      path                 = "/v1/workflows"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    workflows_create = {
      method               = "POST"
      path                 = "/v1/workflows"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    workflows_get = {
      method               = "GET"
      path                 = "/v1/workflows/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    workflows_update = {
      method               = "PUT"
      path                 = "/v1/workflows/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    workflows_delete = {
      method               = "DELETE"
      path                 = "/v1/workflows/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    workflows_verify = {
      method               = "POST"
      path                 = "/v1/workflows/{id}/verify"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    workflows_runs = {
      method               = "GET"
      path                 = "/v1/workflows/{id}/runs"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    custom_tools_list = {
      method               = "GET"
      path                 = "/v1/custom-tools"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    custom_tools_create = {
      method               = "POST"
      path                 = "/v1/custom-tools"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    custom_tools_generate = {
      method               = "POST"
      path                 = "/v1/custom-tools/generate"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    custom_tools_test = {
      method               = "POST"
      path                 = "/v1/custom-tools/test"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    custom_tools_get = {
      method               = "GET"
      path                 = "/v1/custom-tools/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    custom_tools_update = {
      method               = "PUT"
      path                 = "/v1/custom-tools/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    custom_tools_delete = {
      method               = "DELETE"
      path                 = "/v1/custom-tools/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    custom_tools_tool_create = {
      method               = "POST"
      path                 = "/v1/custom-tools/{id}/tools"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    custom_tools_tool_get = {
      method               = "GET"
      path                 = "/v1/custom-tools/{id}/tools/{toolId}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    custom_tools_tool_update = {
      method               = "PUT"
      path                 = "/v1/custom-tools/{id}/tools/{toolId}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    custom_tools_tool_delete = {
      method               = "DELETE"
      path                 = "/v1/custom-tools/{id}/tools/{toolId}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    custom_tools_sessions_list = {
      method               = "GET"
      path                 = "/v1/custom-tools/sessions"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    custom_tools_sessions_create = {
      method               = "POST"
      path                 = "/v1/custom-tools/sessions"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    custom_tools_session_get = {
      method               = "GET"
      path                 = "/v1/custom-tools/sessions/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    custom_tools_session_update = {
      method               = "PATCH"
      path                 = "/v1/custom-tools/sessions/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    custom_tools_session_delete = {
      method               = "DELETE"
      path                 = "/v1/custom-tools/sessions/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    custom_tools_session_turn = {
      method               = "POST"
      path                 = "/v1/custom-tools/sessions/{id}/turn"
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
    support_messages_list = {
      method               = "GET"
      path                 = "/v1/support/messages"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    support_messages_create = {
      method               = "POST"
      path                 = "/v1/support/messages"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    support_message_get = {
      method               = "GET"
      path                 = "/v1/support/messages/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    support_message_reply = {
      method               = "POST"
      path                 = "/v1/support/messages/{id}/reply"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    security_reports_list = {
      method               = "GET"
      path                 = "/v1/security/reports"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    security_reports_create = {
      method               = "POST"
      path                 = "/v1/security/reports"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    vault_providers = {
      method               = "GET"
      path                 = "/v1/vault/providers"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    vault_secrets_list = {
      method               = "GET"
      path                 = "/v1/vault/secrets"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    vault_secrets_create = {
      method               = "POST"
      path                 = "/v1/vault/secrets"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    vault_test_adhoc = {
      method               = "POST"
      path                 = "/v1/vault/test"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    vault_models = {
      method               = "POST"
      path                 = "/v1/vault/models"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    vault_secret_get = {
      method               = "GET"
      path                 = "/v1/vault/secrets/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    vault_secret_update = {
      method               = "PUT"
      path                 = "/v1/vault/secrets/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    vault_secret_delete = {
      method               = "DELETE"
      path                 = "/v1/vault/secrets/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    vault_secret_test = {
      method               = "POST"
      path                 = "/v1/vault/secrets/{id}/test"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    vault_secret_reveal = {
      method               = "POST"
      path                 = "/v1/vault/secrets/{id}/reveal"
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
    # Public, unauthenticated: signed + expiring Langfuse trace links.
    trace_link = {
      method               = "GET"
      path                 = "/v1/traces/{token}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "NONE"
    }
    run_feedback = {
      method               = "PUT"
      path                 = "/v1/feedback/{runId}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    eval_datasets = {
      method               = "GET"
      path                 = "/v1/evals/datasets"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    eval_dataset_create = {
      method               = "POST"
      path                 = "/v1/evals/datasets"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    eval_dataset_detail = {
      method               = "GET"
      path                 = "/v1/evals/datasets/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    eval_dataset_update = {
      method               = "PUT"
      path                 = "/v1/evals/datasets/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    eval_dataset_delete = {
      method               = "DELETE"
      path                 = "/v1/evals/datasets/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    eval_cases = {
      method               = "GET"
      path                 = "/v1/evals/datasets/{id}/cases"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    eval_case_create = {
      method               = "POST"
      path                 = "/v1/evals/datasets/{id}/cases"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    eval_case_delete = {
      method               = "DELETE"
      path                 = "/v1/evals/datasets/{id}/cases/{caseId}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    eval_dataset_runs = {
      method               = "GET"
      path                 = "/v1/evals/datasets/{id}/runs"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    eval_runs = {
      method               = "GET"
      path                 = "/v1/evals/runs"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    eval_run_create = {
      method               = "POST"
      path                 = "/v1/evals/runs"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    eval_run_detail = {
      method               = "GET"
      path                 = "/v1/evals/runs/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    eval_run_delete = {
      method               = "DELETE"
      path                 = "/v1/evals/runs/{id}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    eval_run_cases = {
      method               = "GET"
      path                 = "/v1/evals/runs/{id}/cases"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    eval_run_case_detail = {
      method               = "GET"
      path                 = "/v1/evals/runs/{id}/cases/{caseId}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    lab_traces = {
      method               = "GET"
      path                 = "/v1/lab/traces"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    lab_trace_to_dataset = {
      method               = "POST"
      path                 = "/v1/lab/traces/{traceId}/dataset"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    lab_trace_to_queue = {
      method               = "POST"
      path                 = "/v1/lab/traces/{traceId}/queue"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    lab_datasets = {
      method               = "GET"
      path                 = "/v1/lab/datasets"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    lab_dataset_create = {
      method               = "POST"
      path                 = "/v1/lab/datasets"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    lab_queues = {
      method               = "GET"
      path                 = "/v1/lab/queues"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    lab_queue_create = {
      method               = "POST"
      path                 = "/v1/lab/queues"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    lab_score_configs = {
      method               = "GET"
      path                 = "/v1/lab/score-configs"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    lab_score_config_create = {
      method               = "POST"
      path                 = "/v1/lab/score-configs"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    lab_metrics = {
      method               = "GET"
      path                 = "/v1/lab/metrics"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    lab_playground_run = {
      method               = "POST"
      path                 = "/v1/lab/playground/run"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    lab_playground_judge = {
      method               = "POST"
      path                 = "/v1/lab/playground/judge"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    lab_trace_detail = {
      method               = "GET"
      path                 = "/v1/lab/traces/{traceId}"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    lab_queue_items = {
      method               = "GET"
      path                 = "/v1/lab/queues/{queueId}/items"
      lambda_invoke_arn    = module.user_api[0].invoke_arn
      lambda_function_name = module.user_api[0].function_name
      authorization_type   = "JWT"
    }
    lab_queue_item_score = {
      method               = "POST"
      path                 = "/v1/lab/queues/{queueId}/items/{itemId}"
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
      throttle_burst_limit = 40
      throttle_rate_limit  = 20
    }
    web_search_mcp = {
      method               = "POST"
      path                 = "/mcp/web-search"
      lambda_invoke_arn    = module.web_search[0].invoke_arn
      lambda_function_name = module.web_search[0].function_name
      authorization_type   = "JWT"
      throttle_burst_limit = 20
      throttle_rate_limit  = 10
    }
    code_interpreter_mcp = {
      method               = "POST"
      path                 = "/mcp/code-interpreter"
      lambda_invoke_arn    = module.code_interpreter[0].invoke_arn
      lambda_function_name = module.code_interpreter[0].function_name
      authorization_type   = "JWT"
      throttle_burst_limit = 10
      throttle_rate_limit  = 5
    }
    custom_tools_mcp = {
      method               = "POST"
      path                 = "/mcp/custom-tools"
      lambda_invoke_arn    = module.custom_tools[0].invoke_arn
      lambda_function_name = module.custom_tools[0].function_name
      authorization_type   = "JWT"
      throttle_burst_limit = 20
      throttle_rate_limit  = 10
    }
    http_fetch_mcp = {
      method               = "POST"
      path                 = "/mcp/http-fetch"
      lambda_invoke_arn    = module.http_fetch[0].invoke_arn
      lambda_function_name = module.http_fetch[0].function_name
      authorization_type   = "JWT"
      throttle_burst_limit = 20
      throttle_rate_limit  = 10
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
    admin_users_list = {
      method               = "GET"
      path                 = "/v1/admin/users"
      lambda_invoke_arn    = module.mcp_tester[0].invoke_arn
      lambda_function_name = module.mcp_tester[0].function_name
      authorization_type   = "JWT"
    }
    admin_user_credits = {
      method               = "POST"
      path                 = "/v1/admin/users/{userId}/credits"
      lambda_invoke_arn    = module.mcp_tester[0].invoke_arn
      lambda_function_name = module.mcp_tester[0].function_name
      authorization_type   = "JWT"
    }
    admin_user_reset = {
      method               = "POST"
      path                 = "/v1/admin/users/{userId}/reset"
      lambda_invoke_arn    = module.mcp_tester[0].invoke_arn
      lambda_function_name = module.mcp_tester[0].function_name
      authorization_type   = "JWT"
    }
    admin_support_list = {
      method               = "GET"
      path                 = "/v1/admin/support"
      lambda_invoke_arn    = module.mcp_tester[0].invoke_arn
      lambda_function_name = module.mcp_tester[0].function_name
      authorization_type   = "JWT"
    }
    admin_support_detail = {
      method               = "GET"
      path                 = "/v1/admin/support/{userId}/{ticketId}"
      lambda_invoke_arn    = module.mcp_tester[0].invoke_arn
      lambda_function_name = module.mcp_tester[0].function_name
      authorization_type   = "JWT"
    }
    admin_support_reply = {
      method               = "POST"
      path                 = "/v1/admin/support/{userId}/{ticketId}/reply"
      lambda_invoke_arn    = module.mcp_tester[0].invoke_arn
      lambda_function_name = module.mcp_tester[0].function_name
      authorization_type   = "JWT"
    }
    admin_support_status = {
      method               = "POST"
      path                 = "/v1/admin/support/{userId}/{ticketId}/status"
      lambda_invoke_arn    = module.mcp_tester[0].invoke_arn
      lambda_function_name = module.mcp_tester[0].function_name
      authorization_type   = "JWT"
    }
    admin_security_list = {
      method               = "GET"
      path                 = "/v1/admin/security-reports"
      lambda_invoke_arn    = module.mcp_tester[0].invoke_arn
      lambda_function_name = module.mcp_tester[0].function_name
      authorization_type   = "JWT"
    }
    admin_security_detail = {
      method               = "GET"
      path                 = "/v1/admin/security-reports/{userId}/{reportId}"
      lambda_invoke_arn    = module.mcp_tester[0].invoke_arn
      lambda_function_name = module.mcp_tester[0].function_name
      authorization_type   = "JWT"
    }
    admin_security_status = {
      method               = "POST"
      path                 = "/v1/admin/security-reports/{userId}/{reportId}/status"
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
      throttle_burst_limit = 20
      throttle_rate_limit  = 10
    }
    }, var.enable_agent_runtime && var.agent_worker_image_uri != "" ? {
    # Auth is enforced at the gateway (JWT authorizer); the Lambda only launches
    # a Lambda MicroVM and returns its endpoint + ingress token. Gated on the
    # worker image URI because the control-plane Lambda only exists once the
    # agent runtime is deployed (see deploy-agent-runtime.sh).
    agent_run_session = {
      method               = "POST"
      path                 = "/v1/agent-run/session"
      lambda_invoke_arn    = module.agent_runtime[0].control_plane_invoke_arn
      lambda_function_name = module.agent_runtime[0].control_plane_function_name
      authorization_type   = "JWT"
      throttle_burst_limit = 10
      throttle_rate_limit  = 5
    }
  } : {}) : {}
}
