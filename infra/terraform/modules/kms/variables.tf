variable "name" {
  type        = string
  description = "Alias name (without the alias/ prefix), e.g. get1agent-prod-mcp-connections"
}

variable "description" {
  type        = string
  description = "Human-readable key description"
  default     = ""
}

variable "tags" {
  type    = map(string)
  default = {}
}
