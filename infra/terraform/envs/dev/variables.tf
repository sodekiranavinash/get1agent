variable "aws_region" {
  type        = string
  default     = "us-east-1"
  description = "AWS region for dev resources"
}

variable "package_path" {
  type        = string
  description = "Path to function.zip, relative to infra/terraform/envs/dev"
  default     = "../../../../tools/challan-extractor/dist/function.zip"
}

variable "enable_data_plane" {
  type        = bool
  default     = false
  description = "Create VPC, Kong EC2, and RDS PostgreSQL (free-tier sized)"
}

variable "data_plane_db_name" {
  type        = string
  default     = "get1agent"
  description = "PostgreSQL app database name"
}

variable "data_plane_db_username" {
  type        = string
  default     = "get1agent"
  description = "PostgreSQL master username"
}

variable "data_plane_db_iam_username" {
  type        = string
  default     = "get1agent_app"
  description = "PostgreSQL IAM user for future serverless services"
}

variable "data_plane_api_hostname" {
  type        = string
  default     = "api.get1agent.com"
  description = "Kong proxy hostname (Cloudflare A record)"
}

variable "data_plane_kong_ui_hostname" {
  type        = string
  default     = "kong.get1agent.com"
  description = "Kong Manager UI hostname (Cloudflare A record)"
}
