variable "aws_region" {
  type        = string
  default     = "ap-south-1"
  description = "AWS region for prod resources (API, VPC, RDS, Lambdas)"
}

variable "enable_network" {
  type        = bool
  default     = false
  description = "VPC, subnets, jumpbox (on-demand public IPv4)"
}

variable "enable_rds" {
  type        = bool
  default     = false
  description = "RDS PostgreSQL (requires Network)"
}

variable "enable_api_gateway" {
  type        = bool
  default     = false
  description = "API Gateway HTTP API + Auth0 JWT"
}

variable "enable_backend_lambdas" {
  type        = bool
  default     = false
  description = "Terraform backend Lambdas (e.g. health-check; requires Network + RDS)"
}

variable "enable_ingestion" {
  type        = bool
  default     = false
  description = "S3 -> EventBridge -> SQS -> Step Functions ingestion pipeline"
}

variable "rds_db_name" {
  type    = string
  default = "get1agent"
}

variable "rds_db_username" {
  type    = string
  default = "get1agent"
}

variable "rds_db_iam_username" {
  type    = string
  default = "get1agent_app"
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

variable "enable_api_custom_domain" {
  type    = bool
  default = true
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
