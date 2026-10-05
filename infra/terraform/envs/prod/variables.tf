variable "aws_region" {
  type        = string
  default     = "ap-south-1"
  description = "AWS region for prod resources (API, VPC, RDS, Lambdas)"
}

variable "enable_api_gateway" {
  type        = bool
  default     = false
  description = "API Gateway HTTP API + Auth0 JWT"
}

variable "enable_backend_lambdas" {
  type        = bool
  default     = false
  description = "Terraform backend Lambdas (DynamoDB + S3)"
}

variable "enable_ingestion" {
  type        = bool
  default     = false
  description = "S3 -> EventBridge -> SQS -> Step Functions ingestion pipeline"
}

variable "dynamodb_table_name" {
  type        = string
  default     = "get1agent"
  description = "Single DynamoDB table holding all operational data"
}

variable "vector_bucket_name" {
  type        = string
  default     = "get1agent-prod-vectors"
  description = "S3 Vectors bucket holding the per-user embedding indexes"
}

variable "api_hostname" {
  type    = string
  default = "api.get1agent.com"
}

variable "auth_domain" {
  type    = string
  default = "get1agent.us.auth0.com"
}

variable "auth_audience" {
  type    = string
  default = "https://api.get1agent.com"
}

variable "agent_service_client_id" {
  type        = string
  default     = ""
  description = "Auth0 M2M client id the eval worker uses to run agents server-side (service auth)"
}

variable "agent_service_client_secret" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Auth0 M2M client secret for the eval worker's service token"
}

variable "auth_mgmt_client_id" {
  type        = string
  default     = ""
  description = "Auth0 Management API M2M client id (scope delete:users) for automatic identity erasure"
}

variable "auth_mgmt_client_secret" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Auth0 Management API M2M client secret for automatic identity erasure"
}

variable "auth_token_url" {
  type        = string
  default     = ""
  description = "Auth0 token endpoint for client-credentials; defaults to https://<auth_domain>/oauth/token"
}

variable "enable_api_custom_domain" {
  type    = bool
  default = true
}

variable "stage_throttle_burst_limit" {
  type        = number
  default     = 100
  description = "API Gateway HTTP API stage-level burst limit, common to all routes (requests)"
}

variable "stage_throttle_rate_limit" {
  type        = number
  default     = 50
  description = "API Gateway HTTP API stage-level steady-state rate, common to all routes (requests/second)"
}

variable "knowledge_bases_bucket_name" {
  type        = string
  default     = "get1agent-prod-knowledge-bases"
  description = "Private S3 bucket for knowledge base documents"
}

variable "enable_xray" {
  type        = bool
  default     = true
  description = "X-Ray tracing on the ingestion workers and state machine (records sampled traces)"
}

variable "rerank_region" {
  type        = string
  default     = "us-west-2"
  description = "Region hosting the Bedrock rerank model (not available in ap-south-1)"
}

variable "rerank_model" {
  type        = string
  default     = "amazon.rerank-v1:0"
  description = "Bedrock rerank model id"
}

variable "code_interpreter_timeout_seconds" {
  type        = number
  default     = 240
  description = "Lambda timeout for the code-interpreter MCP server (must exceed the internal exec timeout)"
}

variable "code_interpreter_exec_timeout_seconds" {
  type        = number
  default     = 120
  description = "Internal wall-clock limit for one code execution; the sandbox is stopped when exceeded"
}

variable "code_interpreter_session_timeout_seconds" {
  type        = number
  default     = 900
  description = "AgentCore Code Interpreter session TTL (seconds); reused until it expires"
}

variable "code_interpreter_max_sessions_per_user" {
  type        = number
  default     = 1
  description = "Maximum active AgentCore Code Interpreter sessions per user"
}

variable "web_search_connector_region" {
  type        = string
  default     = "ap-northeast-1"
  description = "Region hosting the built-in AgentCore Web Search connector + its gateway (us-east-1, eu-west-1 or ap-northeast-1; not ap-south-1)"
}

variable "http_fetch_timeout_seconds" {
  type        = number
  default     = 90
  description = "Lambda timeout for the http-fetch MCP tool (must exceed the 60s max request timeout)"
}

variable "http_fetch_allowed_domains" {
  type        = string
  default     = ""
  description = "Optional comma-separated host allowlist for http-fetch (empty allows any public host)"
}

variable "mcp_oauth_redirect_uri" {
  type        = string
  default     = ""
  description = "Public OAuth callback URL for remote MCP connections (defaults to https://<api_hostname>/v1/mcp/oauth/callback)"
}

variable "frontend_url" {
  type        = string
  default     = "https://www.get1agent.com"
  description = "SPA origin the OAuth callback redirects back to"
}

variable "MCP_GITHUB_CLIENT_ID" {
  type        = string
  default     = ""
  description = "Client ID of the get1agent GitHub OAuth App (for the GitHub remote MCP server)"
}

variable "MCP_GITHUB_CLIENT_SECRET" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Client secret of the get1agent GitHub OAuth App (set via TF_VAR_MCP_GITHUB_CLIENT_SECRET)"
}

variable "enable_agent_runtime" {
  type        = bool
  default     = true
  description = "Deploy the AgentCore agent runtime container + streaming proxy"
}

variable "agent_worker_image_uri" {
  type        = string
  default     = ""
  description = "ARM64 ECR image URI for the agent worker container (push the image before apply)"
}

variable "enable_tracing" {
  type        = bool
  default     = true
  description = "Export agent-runtime traces to CloudWatch/X-Ray via AgentCore's ADOT collector"
}

variable "agent_identity_return_url" {
  type        = string
  default     = "https://api.get1agent.com/v1/identity/callback"
  description = "Public URL AgentCore Identity may redirect a user back to"
}

variable "identity_google_client_id" {
  type        = string
  default     = ""
  description = "Google OAuth client id for AgentCore Identity (empty disables the provider)"
}

variable "identity_google_client_secret" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Google OAuth client secret for AgentCore Identity"
}

variable "identity_github_client_id" {
  type        = string
  default     = ""
  description = "GitHub OAuth client id for AgentCore Identity (empty disables the provider)"
}

variable "identity_github_client_secret" {
  type        = string
  default     = ""
  sensitive   = true
  description = "GitHub OAuth client secret for AgentCore Identity"
}

variable "identity_slack_client_id" {
  type        = string
  default     = ""
  description = "Slack OAuth client id for AgentCore Identity (empty disables the provider)"
}

variable "identity_slack_client_secret" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Slack OAuth client secret for AgentCore Identity"
}

variable "browser_allowed_domains" {
  type        = string
  default     = ""
  description = "Comma-separated domain suffixes the AgentCore Browser may open (empty denies all)"
}

variable "bedrock_prompt_cache" {
  type        = string
  default     = "auto"
  description = "Prompt caching mode (auto|anthropic|off)"
}

variable "bedrock_prompt_cache_ttl" {
  type        = string
  default     = ""
  description = "Prompt cache TTL (e.g. 5m, 1h); empty uses the Bedrock default"
}

variable "bedrock_service_tier" {
  type        = string
  default     = "standard"
  description = "Bedrock service tier for chat/agent calls (standard|flex|priority)"
}

variable "bedrock_ingestion_service_tier" {
  type        = string
  default     = "flex"
  description = "Bedrock service tier for ingestion embedding (flex is ~50% cheaper)"
}

variable "bedrock_prompt_router_arn" {
  type        = string
  default     = ""
  description = "Intelligent prompt router ARN; empty disables routing"
}

variable "enable_nova_prompt_router" {
  type        = bool
  default     = true
  description = "Create the default Nova prompt router (Lite <-> Pro cost routing)"
}

variable "bedrock_profile_chat" {
  type        = string
  default     = ""
  description = "Application inference profile ARN for chat (per-feature billing)"
}

variable "bedrock_profile_eval" {
  type        = string
  default     = ""
  description = "Application inference profile ARN for evaluations"
}

variable "bedrock_profile_ingestion" {
  type        = string
  default     = ""
  description = "Application inference profile ARN for ingestion embeddings"
}

variable "enable_guardrail_iaC" {
  type        = bool
  default     = true
  description = "Create the Bedrock guardrail as Terraform (else use an existing GUARDRAIL_ID)"
}

variable "enable_browser" {
  type        = bool
  default     = true
  description = "Create the AgentCore Browser resource + browser tool"
}

variable "online_evaluation_sampling_percentage" {
  type        = number
  default     = 5
  description = "Percentage of live agent traces sampled by AgentCore Evaluations"
}

variable "agent_policy_deny_tools" {
  type        = string
  default     = ""
  description = "Comma-separated tool names the AgentCore Policy always denies"
}

variable "guardrail_id" {
  type        = string
  default     = ""
  description = "Bedrock Guardrail id applied to agent runs (empty disables guardrails)"
}

variable "guardrail_version" {
  type        = string
  default     = "DRAFT"
  description = "Bedrock Guardrail version applied to agent runs"
}

variable "trace_link_secret" {
  type        = string
  default     = ""
  sensitive   = true
  description = "HMAC secret for signed, expiring trace links (set via TF_VAR_trace_link_secret)"
}

variable "agent_run_allowed_origins" {
  type        = list(string)
  default     = ["https://www.get1agent.com", "http://localhost:5173"]
  description = "Origins allowed to call the agent-run endpoints (control plane + MicroVM)"
}
