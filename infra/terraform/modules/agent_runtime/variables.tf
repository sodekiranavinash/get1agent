variable "name" {
  type        = string
  description = "Base name for the runtime + proxy resources"
}

variable "ecr_repository_name" {
  type    = string
  default = "get1agent-prod-agent-worker"
}

variable "container_image_uri" {
  type        = string
  description = "ARM64 ECR image URI for the worker container"
}

variable "proxy_zip" {
  type        = string
  description = "Path to the agent-run proxy Lambda zip"
}

# The proxy is Node.js: Lambda's native response streaming
# (`awslambda.streamifyResponse`) is a Node.js managed-runtime feature.
variable "proxy_runtime" {
  type    = string
  default = "nodejs22.x"
}

variable "proxy_handler" {
  type    = string
  default = "index.handler"
}

variable "proxy_timeout_seconds" {
  type    = number
  default = 900
}

# --- Lambda MicroVM (long-running streaming proxy) ---------------------------

variable "microvm_zip" {
  type        = string
  default     = ""
  description = "Path to the agent-run MicroVM artifact zip (Dockerfile + server)"
}

variable "artifact_bucket" {
  type        = string
  default     = ""
  description = "S3 bucket that holds the MicroVM artifact zip"
}

variable "microvm_artifact_key" {
  type        = string
  default     = "microvms/agent-run.zip"
  description = "S3 key for the MicroVM artifact zip"
}

variable "microvm_max_run_seconds" {
  type        = number
  default     = 1500
  description = "Abort an agent run (AgentCore stream) after this many seconds"
}

variable "dynamodb_table_arns" {
  type    = list(string)
  default = []
}

variable "s3_bucket_arns" {
  type    = list(string)
  default = []
}

variable "s3_vector_bucket_arns" {
  type    = list(string)
  default = []
}

variable "mcp_function_arns" {
  type    = list(string)
  default = []
}

variable "runtime_environment" {
  type        = map(string)
  default     = {}
  description = "Environment variables passed to the AgentCore runtime container"
}

variable "jwt_discovery_url" {
  type        = string
  description = "OIDC discovery URL of the JWT authorizer (Auth0)"
}

variable "jwt_allowed_audience" {
  type    = list(string)
  default = []
}

variable "allowed_origins" {
  type    = list(string)
  default = ["*"]
}

variable "idle_timeout_seconds" {
  type    = number
  default = 900
}

variable "max_lifetime_seconds" {
  type    = number
  default = 28800
}

variable "tags" {
  type    = map(string)
  default = {}
}
