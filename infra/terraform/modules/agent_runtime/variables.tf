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

variable "python_runtime" {
  type    = string
  default = "python3.14"
}

variable "proxy_timeout_seconds" {
  type    = number
  default = 900
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
