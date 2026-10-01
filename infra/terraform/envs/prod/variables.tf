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
  description = "Terraform backend Lambdas (DynamoDB + S3; no VPC/RDS)"
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

variable "auth0_domain" {
  type    = string
  default = "get1agent.us.auth0.com"
}

variable "auth0_audience" {
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

variable "auth0_token_url" {
  type        = string
  default     = ""
  description = "Auth0 token endpoint for client-credentials; defaults to https://<auth0_domain>/oauth/token"
}

variable "upstash_redis_rest_url" {
  type        = string
  default     = ""
  description = "Upstash Redis REST URL for the best-effort cache (embeddings + search)"
}

variable "upstash_redis_rest_token" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Upstash Redis REST token for the best-effort cache"
}

variable "upstash_vector_rest_url" {
  type        = string
  default     = ""
  description = "Upstash Vector REST URL for the semantic cache"
}

variable "upstash_vector_rest_token" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Upstash Vector REST token for the semantic cache"
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

variable "voyage_api_key" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Voyage AI API key for embeddings (set via TF_VAR_voyage_api_key)"
}

variable "voyage_api_base_url" {
  type        = string
  default     = "https://api.voyageai.com/v1"
  description = "Voyage AI API base URL (override for the MongoDB Atlas endpoint)"
}

variable "voyage_text_model" {
  type        = string
  default     = "voyage-4-large"
  description = "Voyage text embedding model"
}

variable "voyage_multimodal_model" {
  type        = string
  default     = "voyage-multimodal-3.5"
  description = "Voyage multimodal embedding model"
}

variable "voyage_rerank_model" {
  type        = string
  default     = "rerank-3"
  description = "Voyage rerank model (opt-in per request)"
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

variable "exa_api_key" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Exa Search API key for the web-search tool (set via TF_VAR_exa_api_key)"
}

variable "exa_api_base_url" {
  type        = string
  default     = "https://api.exa.ai"
  description = "Exa API base URL (override for testing)"
}

variable "web_search_timeout_seconds" {
  type        = number
  default     = 60
  description = "Lambda timeout for the web-search MCP tool (deep search can take ~40s)"
}

variable "web_search_max_results" {
  type        = number
  default     = 25
  description = "Hard cap on Exa results per web-search call (cost guard)"
}

variable "http_fetch_timeout_seconds" {
  type        = number
  default     = 60
  description = "Lambda timeout for the http-fetch MCP tool"
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

variable "GITHUB_MCP_CLIENT_ID" {
  type        = string
  default     = ""
  description = "Client ID of the get1agent GitHub OAuth App (for the GitHub remote MCP server)"
}

variable "GITHUB_MCP_CLIENT_SECRET" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Client secret of the get1agent GitHub OAuth App (set via TF_VAR_GITHUB_MCP_CLIENT_SECRET)"
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

variable "opencode_api_key" {
  type        = string
  default     = ""
  sensitive   = true
  description = "OpenCode Go API key for agent LLMs (set via TF_VAR_opencode_api_key)"
}

variable "opencode_base_url" {
  type        = string
  default     = "https://opencode.ai/zen/go/v1"
  description = "OpenCode Go OpenAI-compatible base URL"
}

variable "enable_langfuse" {
  type        = bool
  default     = true
  description = "Send agent-runtime traces to Langfuse (disables AgentCore's ADOT exporter for the runtime)"
}

variable "langfuse_host" {
  type        = string
  default     = "https://cloud.langfuse.com"
  description = "Langfuse base URL (US: https://us.cloud.langfuse.com; self-hosted: your URL)"
}

variable "langfuse_public_key" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Langfuse public key for agent tracing (set via TF_VAR_langfuse_public_key)"
}

variable "langfuse_secret_key" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Langfuse secret key for agent tracing (set via TF_VAR_langfuse_secret_key)"
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
