variable "aws_region" {
  type        = string
  default     = "ap-south-1"
  description = "AWS region for prod resources (API, VPC, RDS, Lambdas)"
}

variable "package_path" {
  type        = string
  description = "Path to function.zip, relative to infra/terraform/envs/prod"
  default     = "../../../../tools/challan-extractor/dist/function.zip"
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

variable "enable_tool_lambdas" {
  type        = bool
  default     = false
  description = "Terraform tool Lambdas (e.g. challan-extractor)"
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
