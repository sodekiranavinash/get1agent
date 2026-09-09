variable "name_prefix" {
  type        = string
  description = "Prefix for resource names (e.g. get1agent-prod)"
}

variable "api_hostname" {
  type        = string
  description = "Public API hostname (e.g. api.get1agent.com)"
}

variable "enable_custom_domain" {
  type        = bool
  default     = false
  description = "Create ACM cert + api.<domain> mapping (requires DNS validation CNAME in Cloudflare)"
}

variable "auth0_domain" {
  type        = string
  description = "Auth0 tenant domain (e.g. get1agent.us.auth0.com)"
}

variable "auth0_audience" {
  type        = string
  description = "Auth0 API identifier — must match frontend authorizationParams.audience"
}

variable "stage_name" {
  type        = string
  default     = "$default"
  description = "API Gateway HTTP API stage name"
}

variable "stage_throttle_burst_limit" {
  type        = number
  default     = 100
  description = "Stage-level burst limit (requests)"
}

variable "stage_throttle_rate_limit" {
  type        = number
  default     = 50
  description = "Stage-level steady-state rate limit (requests per second)"
}

variable "cors_allow_origins" {
  type        = list(string)
  default     = ["https://www.get1agent.com", "http://localhost:5173"]
  description = "CORS allowed origins for browser clients"
}

variable "lambda_routes" {
  type = map(object({
    method               = string
    path                 = string
    lambda_invoke_arn    = string
    lambda_function_name = string
    authorization_type   = optional(string, "JWT")
    throttle_burst_limit = optional(number)
    throttle_rate_limit  = optional(number)
  }))
  default     = {}
  description = "Lambda-backed routes (key = stable route id)"
}

variable "tags" {
  type    = map(string)
  default = {}
}
