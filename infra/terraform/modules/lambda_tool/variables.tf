variable "name" {
  type        = string
  description = "Lambda function name, e.g. get1agent-prod-challan-extractor"
}

variable "filename" {
  type        = string
  description = "Path to the deployment zip containing bootstrap"
}

variable "source_code_hash" {
  type        = string
  description = "Base64 sha256 of the zip; pass filebase64sha256(filename) from the caller"
}

variable "memory_size" {
  type    = number
  default = 256
}

variable "timeout" {
  type    = number
  default = 25
}

variable "architectures" {
  type    = list(string)
  default = ["arm64"]
}

variable "environment" {
  type    = map(string)
  default = {}
}

variable "log_retention_days" {
  type    = number
  default = 7
}

variable "allowed_invoke_principal" {
  type        = string
  default     = ""
  description = "Optional principal (e.g. MCP Gateway role ARN) granted lambda:InvokeFunction"
}

variable "tags" {
  type    = map(string)
  default = {}
}
